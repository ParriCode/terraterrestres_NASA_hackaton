import type { TransferResponse, TransferState, TransferSample } from '../types/transfer'
import type { EarthMoonEphemeris, SunDirectionEphemeris } from '../api/ephemerides'
import { directionToScene, sampleCubic, toScene, vAdd, vCross, vDot, vLength, vMul, vNormalize, vSub } from '../utils/icrf3d'
import type { Vector3 } from '../utils/icrf3d'
import { capBodyRadius, shipScaleForClearance } from '../utils/visualScale3d'
import { frameToIcrf, icrfToEcliptic } from '../utils/heliocentric'

/** En Tierra–Luna solo renderizamos la fase de salida de una misión marciana.
 * No se eliminan datos de la misión; la ruta completa permanece en el visor solar. */
function localDepartureSamples(samples: TransferSample[]): TransferSample[] {
  const local = samples.filter((sample, index) => index < 2 || Math.hypot(
    sample.position_m[0] - sample.body_positions_m.earth[0],
    sample.position_m[1] - sample.body_positions_m.earth[1],
    sample.position_m[2] - sample.body_positions_m.earth[2],
  ) <= 7.5e9)
  return local.length > 1 ? local : samples.slice(0, 2)
}

/** Visor WebGL sin dependencias ni motores de física en el navegador. */
type Mat4 = Float32Array
type Focus = 'system' | 'earth' | 'moon' | 'ship'
type Mesh = { vertices: WebGLBuffer; indices: WebGLBuffer; length: number }
type Track = { buffer: WebGLBuffer; count: number }
type Path = Track & { times: Float64Array }

const VERTEX_SHADER = `
attribute vec3 aPosition;
attribute vec3 aNormal;
uniform mat4 uVP;
uniform mat4 uModel;
varying vec3 vNormal;
varying vec3 vSurface;
varying vec3 vWorld;
void main() {
  vec4 wp = uModel * vec4(aPosition, 1.0);
  vWorld = wp.xyz;
  vNormal = normalize(mat3(uModel) * aNormal);
  vSurface = aPosition;
  gl_Position = uVP * wp;
}
`
const FRAGMENT_SHADER = `
precision highp float;
varying vec3 vNormal;
varying vec3 vSurface;
varying vec3 vWorld;
uniform vec3 uCamera;
uniform vec3 uSun;
uniform vec3 uColor;
uniform float uKind;
uniform float uAlpha;
uniform float uTime;
float hash3(vec3 p) { p = fract(p * 0.1031); p += dot(p, p.yzx + 33.33); return fract((p.x + p.y) * p.z); }
float noise3(vec3 p) {
  vec3 i = floor(p), f = fract(p); f = f*f*(3.0 - 2.0*f);
  return mix(mix(mix(hash3(i), hash3(i+vec3(1,0,0)), f.x), mix(hash3(i+vec3(0,1,0)), hash3(i+vec3(1,1,0)), f.x), f.y),
    mix(mix(hash3(i+vec3(0,0,1)), hash3(i+vec3(1,0,1)), f.x), mix(hash3(i+vec3(0,1,1)), hash3(i+vec3(1,1,1)), f.x), f.y), f.z);
}
float fbm(vec3 p) { return 0.55*noise3(p) + 0.28*noise3(p*2.13) + 0.17*noise3(p*4.24); }
void main() {
  vec3 n = normalize(vNormal);
  vec3 eye = normalize(uCamera - vWorld);
  vec3 p = normalize(vSurface);
  float sun = max(dot(n, normalize(uSun)), 0.0);
  float lit = 0.10 + 0.90*sun;
  vec3 rgb = uColor;
  float alpha = uAlpha;
  if (uKind < 0.5) { // Tierra, continentes, océanos, nubes y casquetes proceduralmente coloreados
    float landField = fbm(p*3.7 + vec3(0.3,1.7,2.1)) + 0.15*noise3(p*1.6);
    float land = smoothstep(0.43, 0.55, landField);
    vec3 ocean = mix(vec3(0.012,0.09,0.27), vec3(0.015,0.30,0.56), noise3(p*12.0));
    vec3 grass = mix(vec3(0.09,0.24,0.12), vec3(0.36,0.45,0.20), noise3(p*9.0));
    grass = mix(grass, vec3(0.59,0.47,0.27), smoothstep(0.60,0.80, noise3(p*13.0)));
    vec3 surface = mix(ocean, grass, land);
    float ice = smoothstep(0.78,0.96,abs(p.y)+0.045*noise3(p*17.0));
    surface = mix(surface,vec3(0.86,0.96,0.99),ice);
    float clouds = smoothstep(0.62,0.74,fbm(p*8.0 + vec3(4.2,0.1,uTime*0.000003)));
    surface = mix(surface, vec3(0.81,0.91,1.0), clouds*0.72);
    rgb = surface*(0.12 + 0.99*sun) + vec3(0.015,0.045,0.11)*pow(1.0-max(dot(n,eye),0.0),2.5);
  } else if (uKind < 1.5) { // Relieve lunar y mares basálticos
    float relief = fbm(p*10.0 + vec3(2.1,0.8,4.9));
    float maria = smoothstep(0.48,0.71,fbm(p*3.0));
    float spots = pow(noise3(p*66.0), 7.0);
    rgb = mix(vec3(0.42,0.43,0.47),vec3(0.64,0.63,0.60),relief);
    rgb = mix(rgb,vec3(0.25,0.27,0.31),maria*0.53);
    rgb -= spots*0.11;
    rgb *= 0.16 + 0.92*sun;
  } else if (uKind > 5.5) { // Planetas: minerales y relieve
    float terrain = fbm(p*8.0 + vec3(1.2,0.5,3.4));
    float craters = pow(noise3(p*64.0),7.0);
    rgb = mix(uColor*0.48, uColor*1.15, terrain) - vec3(0.12)*craters;
    rgb *= 0.13 + 0.96*sun;
  } else if (uKind < 2.5) { // Geometría del cohete
    rgb = uColor*(0.30 + 0.72*sun) + uColor*0.06*pow(max(dot(reflect(-normalize(uSun),n),eye),0.0),18.0);
  } else if (uKind > 3.5 && uKind < 4.5) { // Sol representativo, emisivo y fuera de escala
    rgb = vec3(1.0,0.70,0.22) + 0.16*vec3(1.0,0.9,0.5)*noise3(p*17.0 + uTime*0.00005);
  } else if (uKind > 4.5) { // Corona del sol
    rgb = vec3(1.0,0.55,0.12);
    alpha *= 0.18 * pow(1.0-max(dot(n,eye),0.0),1.1);
  } else { // Halo atmosférico, solo decorativo
    float rim = pow(1.0-max(dot(n,eye),0.0),2.6);
    rgb = vec3(0.04,0.45,0.93)*(0.25 + 0.65*sun);
    alpha *= rim*0.63;
  }
  gl_FragColor = vec4(rgb,alpha);
}
`
const DOT_VERTEX = `
attribute vec3 aPosition;
uniform mat4 uVP;
uniform float uSize;
void main() { gl_Position = uVP * vec4(aPosition, 1.0); gl_PointSize = uSize; }
`
const DOT_FRAGMENT = `
precision mediump float;
uniform vec3 uColor;
uniform float uAlpha;
uniform float uPoints;
void main() {
  float a = uAlpha;
  if (uPoints > 0.5) {
    float r = length(gl_PointCoord - 0.5)*2.0;
    a *= 1.0 - smoothstep(0.40,1.0,r);
  }
  gl_FragColor = vec4(uColor,a);
}
`

function shader(gl: WebGLRenderingContext, type: number, code: string): WebGLShader {
  const result = gl.createShader(type)
  if (!result) throw Error('No se pudo crear el shader WebGL')
  gl.shaderSource(result, code); gl.compileShader(result)
  if (!gl.getShaderParameter(result, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(result)
    gl.deleteShader(result); throw Error(`Error WebGL shader: ${message}`)
  }
  return result
}
function program(gl: WebGLRenderingContext, vert: string, frag: string): WebGLProgram {
  const result = gl.createProgram()
  if (!result) throw Error('No se pudo crear el programa WebGL')
  const vs = shader(gl, gl.VERTEX_SHADER, vert), fs = shader(gl, gl.FRAGMENT_SHADER, frag)
  gl.attachShader(result, vs); gl.attachShader(result, fs); gl.linkProgram(result)
  gl.deleteShader(vs); gl.deleteShader(fs)
  if (!gl.getProgramParameter(result, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(result)
    gl.deleteProgram(result); throw Error(`Error WebGL: ${message}`)
  }
  return result
}
function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Float32Array(16)
  for (let c=0;c<4;c++) for (let r=0;r<4;r++) for (let k=0;k<4;k++) out[c*4+r] += a[k*4+r]*b[c*4+k]
  return out
}
function perspective(aspect: number): Mat4 {
  const f = 1/Math.tan(43*Math.PI/360), near=.04, far=2200
  return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0])
}
function lookAt(eye: Vector3, target: Vector3): Mat4 {
  const z=vNormalize(vSub(eye,target)), x=vNormalize(vCross([0,1,0],z)), y=vCross(z,x)
  return new Float32Array([
    x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,
    -vDot(x,eye),-vDot(y,eye),-vDot(z,eye),1,
  ])
}
function model(position: Vector3, scale: number, angle=0): Mat4 {
  const c=Math.cos(angle)*scale, s=Math.sin(angle)*scale
  return new Float32Array([c,0,-s,0,0,scale,0,0,s,0,c,0,...position,1])
}
function rocketModel(position: Vector3, velocity: Vector3, scale: number): Mat4 {
  const up = vNormalize(velocity), reference: Vector3 = Math.abs(up[2])>.9 ? [0,1,0] : [0,0,1]
  const right=vNormalize(vCross(up,reference)), forward=vCross(right,up)
  return new Float32Array([
    right[0]*scale,right[1]*scale,right[2]*scale,0,
    up[0]*scale,up[1]*scale,up[2]*scale,0,
    forward[0]*scale,forward[1]*scale,forward[2]*scale,0,
    ...position,1,
  ])
}
function hexRgb(hex: string): Vector3 {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return [.42,.94,.85]
  return [1,3,5].map(n => parseInt(hex.slice(n,n+2),16)/255) as Vector3
}
function createMesh(gl: WebGLRenderingContext, vertexData: number[], indices: number[]): Mesh {
  const v=gl.createBuffer(), i=gl.createBuffer()
  if (!v || !i) throw Error('Memoria gráfica insuficiente')
  gl.bindBuffer(gl.ARRAY_BUFFER,v); gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(vertexData),gl.STATIC_DRAW)
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,i); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(indices),gl.STATIC_DRAW)
  return {vertices:v,indices:i,length:indices.length}
}
function sphere(gl: WebGLRenderingContext): Mesh {
  const vertices:number[]=[], indices:number[]=[], lat=46, lon=88
  for(let j=0;j<=lat;j++) {
    const theta=j*Math.PI/lat
    for(let i=0;i<=lon;i++) {
      const phi=2*Math.PI*i/lon
      const p:Vector3=[Math.sin(theta)*Math.cos(phi),Math.cos(theta),Math.sin(theta)*Math.sin(phi)]
      vertices.push(...p,...p)
    }
  }
  for(let j=0;j<lat;j++) for(let i=0;i<lon;i++) {
    const a=j*(lon+1)+i,b=a+lon+1
    indices.push(a,a+1,b,b,a+1,b+1)
  }
  return createMesh(gl,vertices,indices)
}
function rocketParts(gl: WebGLRenderingContext): Mesh[] {
  function makePiece(r0:number,r1:number,y0:number,y1:number):Mesh {
    const vertices:number[]=[], indices:number[]=[], sides=18
    const slope=(r0-r1)/Math.max(y1-y0,.001)
    for(let j=0;j<=1;j++) for(let i=0;i<=sides;i++) {
      const angle=i*2*Math.PI/sides, cos=Math.cos(angle),sin=Math.sin(angle)
      const normal=vNormalize([cos,slope,sin])
      vertices.push((j?r1:r0)*cos,j?y1:y0,(j?r1:r0)*sin,...normal)
    }
    for(let i=0;i<sides;i++) {const a=i,b=a+sides+1; indices.push(a,b,a+1,b,b+1,a+1)}
    return createMesh(gl,vertices,indices)
  }
  const fins:number[]=[], index:number[]=[]
  for(let j=0;j<3;j++) {
    const theta=j*2*Math.PI/3
    const radial:Vector3=[Math.cos(theta),0,Math.sin(theta)]
    const side:Vector3=[-Math.sin(theta),0,Math.cos(theta)]
    const points=[vAdd(vMul(radial,.18),[0,-.35,0]),vAdd(vMul(radial,.5),[0,-.57,0]),vAdd(vMul(radial,.18),[0,.12,0])]
    const start=fins.length/6
    for(const p of points) fins.push(...p,...side)
    index.push(start,start+1,start+2,start+2,start+1,start)
  }
  return [makePiece(.19,.19,-.48,.42), makePiece(.19,.02,.42,.92), createMesh(gl,fins,index),makePiece(.12,.05,-.69,-.48)]
}
function createTrack(gl:WebGLRenderingContext,points:Vector3[]):Track {
  const buffer=gl.createBuffer()
  if(!buffer) throw Error('No hay memoria para la trayectoria 3D')
  gl.bindBuffer(gl.ARRAY_BUFFER,buffer)
  gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(points.flat()),gl.STATIC_DRAW)
  return {buffer,count:points.length}
}
function createStars(gl:WebGLRenderingContext):Track {
  let seed=0x13579bdf
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296}
  const points:Vector3[]=[]
  for(let i=0;i<1900;i++) {
    const z=2*random()-1,theta=random()*2*Math.PI,r=700
    const s=Math.sqrt(1-z*z)
    points.push([r*s*Math.cos(theta),r*z,r*s*Math.sin(theta)])
  }
  return createTrack(gl,points)
}

/** Reutilizar recursos GPU entre fotogramas; el backend sigue siendo autoridad de posiciones. */
export class SpaceRenderer {
  private readonly gl:WebGLRenderingContext
  private readonly meshProgram:WebGLProgram
  private readonly dotProgram:WebGLProgram
  private readonly globe:Mesh
  private readonly rocket:Mesh[]
  private readonly stars:Track
  private readonly shipPoint:Track
  private earthTrack:Track|null=null
  private moonTrack:Track|null=null
  private route:Path|null=null
  private transfer:TransferResponse|null=null
  private preview:EarthMoonEphemeris|null=null
  private current:TransferState|null=null
  private sun:SunDirectionEphemeris|null=null
  private date=new Date()
  private color='#64ead5'
  private showRoute=true
  private enhanced=true
  private tracksEnabled=true
  private camera={yaw:-.55,pitch:.36,distance:71,target:[0,0,0] as Vector3}
  private home={target:[0,0,0] as Vector3,distance:71}
  private focus:Focus='system'
  private viewProj:Mat4=new Float32Array(16)
  private eye:Vector3=[0,0,80]
  private raf=0
  private active=true
  private labels:Record<'earth'|'moon'|'ship',HTMLElement|null>
  private lastPosition:{earth:Vector3|null;moon:Vector3|null;ship:Vector3|null}={earth:null,moon:null,ship:null}
  private dragging:{x:number;y:number;button:number;target:Vector3}|null=null
  private minDistances={earth:Infinity,moon:Infinity}
  private resizeObserver:ResizeObserver
  private cleanups:(()=>void)[]=[]

  private canvas:HTMLCanvasElement
  private sunArrow:HTMLElement|null
  constructor(canvas:HTMLCanvasElement, labels:{earth:HTMLElement|null;moon:HTMLElement|null;ship:HTMLElement|null}, sunArrow:HTMLElement|null=null) {
    this.canvas=canvas;this.sunArrow=sunArrow
    const gl=canvas.getContext('webgl',{antialias:true,alpha:false,powerPreference:'high-performance'})
    if(!gl) throw Error('Tu navegador no dispone de WebGL. Activa la aceleración por hardware para usar el visor 3D.')
    this.gl=gl; this.labels=labels
    this.meshProgram=program(gl,VERTEX_SHADER,FRAGMENT_SHADER)
    this.dotProgram=program(gl,DOT_VERTEX,DOT_FRAGMENT)
    this.globe=sphere(gl)
    this.rocket=rocketParts(gl)
    this.stars=createStars(gl)
    this.shipPoint=createTrack(gl,[[0,0,0]])
    gl.bindBuffer(gl.ARRAY_BUFFER,this.shipPoint.buffer)
    gl.bufferData(gl.ARRAY_BUFFER,12,gl.DYNAMIC_DRAW)
    gl.enable(gl.DEPTH_TEST)
    gl.depthFunc(gl.LEQUAL)
    this.attachEvents()
    this.resizeObserver=new ResizeObserver(()=>this.resize())
    this.resizeObserver.observe(canvas)
    this.resize()
    this.frame()
  }
  private attachEvents() {
    const on=(event:string,listener:EventListener,options?:AddEventListenerOptions)=>{
      this.canvas.addEventListener(event,listener,options)
      this.cleanups.push(()=>this.canvas.removeEventListener(event,listener,options))
    }
    on('pointerdown',((e:PointerEvent)=>{
      if(e.button!==0 && e.button!==2)return
      this.dragging={x:e.clientX,y:e.clientY,button:e.button,target:[...this.camera.target]}
      this.canvas.setPointerCapture(e.pointerId)
    }) as EventListener)
    on('pointermove',((e:PointerEvent)=>{
      if(!this.dragging)return
      const dx=e.clientX-this.dragging.x,dy=e.clientY-this.dragging.y
      if(this.dragging.button===0) {
        this.camera.yaw-=dx*.006
        this.camera.pitch=Math.max(-1.43,Math.min(1.43,this.camera.pitch-dy*.006))
        this.dragging.x=e.clientX;this.dragging.y=e.clientY
      } else {
        const {yaw,pitch,distance}=this.camera
        const right:Vector3=[Math.cos(yaw),0,-Math.sin(yaw)]
        const up:Vector3=[-Math.sin(pitch)*Math.sin(yaw),Math.cos(pitch),-Math.sin(pitch)*Math.cos(yaw)]
        const factor=distance*.0014
        this.camera.target=vAdd(this.dragging.target,vAdd(vMul(right,-dx*factor),vMul(up,dy*factor)))
        this.focus='system'
      }
    }) as EventListener)
    const end=()=>{this.dragging=null}
    on('pointerup',end as EventListener);on('pointercancel',end as EventListener);on('lostpointercapture',end as EventListener)
    on('wheel',((e:WheelEvent)=>{e.preventDefault();this.zoom(Math.exp(Math.sign(e.deltaY)*.17))}) as EventListener,{passive:false})
    on('contextmenu',((e:MouseEvent)=>e.preventDefault()) as EventListener)
  }
  private resize() {
    const gl=this.gl, rect=this.canvas.getBoundingClientRect()
    if(rect.width===0||rect.height===0)return
    const ratio=Math.min(window.devicePixelRatio||1,1.8)
    const factor=Math.min(1,2100/Math.max(rect.width*ratio,rect.height*ratio))
    const w=Math.max(1,Math.round(rect.width*ratio*factor)),h=Math.max(1,Math.round(rect.height*ratio*factor))
    if(this.canvas.width!==w||this.canvas.height!==h){this.canvas.width=w;this.canvas.height=h}
    gl.viewport(0,0,w,h)
  }
  setMission(transfer:TransferResponse|null,color:string,visible:boolean) {
    const changed=transfer!==this.transfer
    this.transfer=transfer;this.color=color;this.showRoute=visible
    if(!changed)return
    const gl=this.gl
    if(this.route)gl.deleteBuffer(this.route.buffer)
    if(this.earthTrack)gl.deleteBuffer(this.earthTrack.buffer)
    if(this.moonTrack)gl.deleteBuffer(this.moonTrack.buffer)
    this.route=this.earthTrack=this.moonTrack=null
    this.minDistances={earth:Infinity,moon:Infinity}
    if(transfer && transfer.samples.length>=2){
      const samples=transfer.destination === 'mars' ? localDepartureSamples(transfer.samples) : transfer.samples,basis=transfer.basis_icrf
      const earth=samples.map(s=>toScene(s.body_positions_m.earth,basis))
      const moon=samples.map(s=>toScene(s.body_positions_m.moon,basis))
      this.earthTrack=createTrack(gl,earth);this.moonTrack=createTrack(gl,moon)
      const pts:Vector3[]=[],ts:number[]=[]
      for(let i=0;i<samples.length-1;i++){
        const a=samples[i],b=samples[i+1],duration=b.t_s-a.t_s
        const pa=toScene(a.position_m,basis),pb=toScene(b.position_m,basis)
        const va=toScene(a.velocity_m_s,basis),vb=toScene(b.velocity_m_s,basis)
        // 6 subdivisiones para mostrar arcos suaves, sin volver a integrar física.
        for(let j=0;j<6;j++){
          const t=j/6
          const point=sampleCubic(pa,va,pb,vb,duration,t)
          pts.push(point)
          // Detectar proximidad también entre muestras; el tamaño visual
          // no puede convertir una órbita real en una colisión ficticia.
          const e=vAdd(vMul(earth[i],1-t),vMul(earth[i+1],t))
          const m=vAdd(vMul(moon[i],1-t),vMul(moon[i+1],t))
          this.minDistances.earth=Math.min(this.minDistances.earth,vLength(vSub(point,e)))
          this.minDistances.moon=Math.min(this.minDistances.moon,vLength(vSub(point,m)))
          ts.push(a.t_s+duration*t)
        }
      }
      const last=toScene(samples[samples.length-1].position_m,basis)
      pts.push(last)
      this.minDistances.earth=Math.min(this.minDistances.earth,vLength(vSub(last,earth[earth.length-1])))
      this.minDistances.moon=Math.min(this.minDistances.moon,vLength(vSub(last,moon[moon.length-1])))
      ts.push(samples[samples.length-1].t_s)
      this.route={...createTrack(gl,pts),times:new Float64Array(ts)}
      this.frameHome([...earth,...moon,...pts])
    }else if(this.preview){this.frameHome([toScene(this.preview.body_positions_m.earth),toScene(this.preview.body_positions_m.moon)])}
  }
  setPreview(data:EarthMoonEphemeris|null) {
    this.preview=data
    if(!this.transfer&&data)this.frameHome([toScene(data.body_positions_m.earth),toScene(data.body_positions_m.moon)])
  }
  setFrame(state:TransferState|null,date:Date,sun:SunDirectionEphemeris|null){this.current=state;this.date=date;this.sun=sun}
  setEnhanced(value:boolean){this.enhanced=value}
  setTracks(value:boolean){this.tracksEnabled=value}
  zoom(factor:number){this.camera.distance=Math.max(.85,Math.min(1000,this.camera.distance*factor))}
  focusOn(value:Focus){
    if(value==='system'){this.focus='system';this.camera.target=[...this.home.target];this.camera.distance=this.home.distance;this.camera.yaw=-.55;this.camera.pitch=.36;return}
    const target=this.lastPosition[value]
    if(!target)return
    this.focus=value;this.camera.target=[...target]
    this.camera.distance=value==='earth'?9:value==='moon'?5.5:4.5
  }
  private frameHome(points:Vector3[]) {
    if(!points.length)return
    const x=points.map(p=>p[0]),y=points.map(p=>p[1]),z=points.map(p=>p[2])
    const target:Vector3=[(Math.min(...x)+Math.max(...x))/2,(Math.min(...y)+Math.max(...y))/2,(Math.min(...z)+Math.max(...z))/2]
    let radius=0
    for(const p of points)radius=Math.max(radius,vLength(vSub(p,target)))
    const distance=Math.max(26,Math.min(950,radius*2.85+5))
    this.home={target,distance}
    this.focusOn('system')
  }
  private bindMesh(mesh:Mesh){
    const gl=this.gl,p=this.meshProgram
    gl.bindBuffer(gl.ARRAY_BUFFER,mesh.vertices)
    const pos=gl.getAttribLocation(p,'aPosition'),normal=gl.getAttribLocation(p,'aNormal')
    gl.enableVertexAttribArray(pos);gl.enableVertexAttribArray(normal)
    gl.vertexAttribPointer(pos,3,gl.FLOAT,false,24,0)
    gl.vertexAttribPointer(normal,3,gl.FLOAT,false,24,12)
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,mesh.indices)
  }
  private drawMesh(mesh:Mesh,matrix:Mat4,color:Vector3,kind:number,alpha=1){
    const gl=this.gl,p=this.meshProgram
    gl.useProgram(p);this.bindMesh(mesh)
    gl.uniformMatrix4fv(gl.getUniformLocation(p,'uVP'),false,this.viewProj)
    gl.uniformMatrix4fv(gl.getUniformLocation(p,'uModel'),false,matrix)
    gl.uniform3fv(gl.getUniformLocation(p,'uCamera'),this.eye)
    const light:Vector3=this.sun ? vNormalize(directionToScene(this.sun.direction_icrf)) : vNormalize([.6,.36,.75])
    gl.uniform3fv(gl.getUniformLocation(p,'uSun'),light)
    gl.uniform3fv(gl.getUniformLocation(p,'uColor'),color)
    gl.uniform1f(gl.getUniformLocation(p,'uKind'),kind)
    gl.uniform1f(gl.getUniformLocation(p,'uAlpha'),alpha)
    gl.uniform1f(gl.getUniformLocation(p,'uTime'),this.date.getTime()/1000)
    gl.drawElements(gl.TRIANGLES,mesh.length,gl.UNSIGNED_SHORT,0)
  }
  private drawTrack(track:Track|null,rgb:Vector3,alpha:number,mode:number,size=2,start=0,count?:number){
    if(!track||track.count===0)return
    const gl=this.gl,p=this.dotProgram
    gl.useProgram(p)
    const pos=gl.getAttribLocation(p,'aPosition')
    gl.bindBuffer(gl.ARRAY_BUFFER,track.buffer);gl.enableVertexAttribArray(pos)
    gl.vertexAttribPointer(pos,3,gl.FLOAT,false,0,0)
    gl.uniformMatrix4fv(gl.getUniformLocation(p,'uVP'),false,this.viewProj)
    gl.uniform3fv(gl.getUniformLocation(p,'uColor'),rgb)
    gl.uniform1f(gl.getUniformLocation(p,'uAlpha'),alpha)
    gl.uniform1f(gl.getUniformLocation(p,'uSize'),size)
    gl.uniform1f(gl.getUniformLocation(p,'uPoints'),mode===gl.POINTS?1:0)
    gl.drawArrays(mode,start,count??track.count)
  }
  private bodyRadii() {
    const earthPhysical=(this.transfer?.bodies.earth.radius_m??6371000)/10000000
    const moonPhysical=(this.transfer?.bodies.moon.radius_m??1737400)/10000000
    return {
      earth:capBodyRadius(earthPhysical,this.enhanced?2.65:1,this.minDistances.earth),
      moon:capBodyRadius(moonPhysical,this.enhanced?5.3:1,this.minDistances.moon),
    }
  }
  private updateSunArrow() {
    if(!this.sunArrow || !this.sun)return
    const dir=vNormalize(directionToScene(this.sun.direction_icrf))
    const {yaw,pitch}=this.camera
    const right:Vector3=[Math.cos(yaw),0,-Math.sin(yaw)]
    const up:Vector3=[-Math.sin(pitch)*Math.sin(yaw),Math.cos(pitch),-Math.sin(pitch)*Math.cos(yaw)]
    const dx=vDot(dir,right),dy=-vDot(dir,up)
    if(Math.hypot(dx,dy)<1e-5) {
      this.sunArrow.style.opacity='.4'
    } else {
      this.sunArrow.style.opacity='1'
      this.sunArrow.style.transform=`rotate(${Math.atan2(dy,dx)*180/Math.PI}deg)`
    }
  }
  private updateLabels() {
    const w=this.canvas.clientWidth,h=this.canvas.clientHeight
    for(const key of ['earth','moon','ship'] as const){
      const label=this.labels[key],p=this.lastPosition[key]
      if(!label)continue
      if(!p || (key==='ship'&&!this.showRoute)){label.style.display='none';continue}
      const m=this.viewProj
      const x=m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12]
      const y=m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13]
      const z=m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14]
      const cw=m[3]*p[0]+m[7]*p[1]+m[11]*p[2]+m[15]
      const px=(x/cw*.5+.5)*w,py=(-y/cw*.5+.5)*h
      const visible=cw>0 && z/cw<1 && px>=0&&px<=w&&py>=0&&py<=h
      label.style.display=visible?'block':'none'
      if(visible){
        label.style.left=`${px}px`;label.style.top=`${py}px`
        const radii=this.bodyRadii()
        const radius = key==='earth' ? radii.earth : key==='moon' ? radii.moon : .12
        const pixelRadius = Math.min(150, radius*Math.abs(m[5])*h/(2*cw))
        label.style.setProperty('--object-offset',`${Math.max(14,pixelRadius+8)}px`)
      }
    }
  }
  private render=()=>{
    const gl=this.gl
    if(!this.canvas.width||!this.canvas.height)return
    const earth=this.transfer ? (this.current ? toScene(this.current.earth_m,this.transfer.basis_icrf) : null) : this.preview ? toScene(this.preview.body_positions_m.earth) : null
    const moon=this.transfer ? (this.current ? toScene(this.current.moon_m,this.transfer.basis_icrf) : null) : this.preview ? toScene(this.preview.body_positions_m.moon) : null
    const shipRaw=this.current&&this.transfer?toScene(this.current.position_m,this.transfer.basis_icrf):null
    const ship=this.transfer?.destination === 'mars' && shipRaw && earth && vLength(vSub(shipRaw,earth)) > 750 ? null : shipRaw
    this.lastPosition={earth,moon,ship}
    if(this.focus!=='system'&&this.lastPosition[this.focus])this.camera.target=[...this.lastPosition[this.focus]!]
    const {yaw,pitch,distance,target}=this.camera
    const offset:Vector3=[distance*Math.cos(pitch)*Math.sin(yaw),distance*Math.sin(pitch),distance*Math.cos(pitch)*Math.cos(yaw)]
    this.eye=vAdd(target,offset)
    this.viewProj=multiply(perspective(this.canvas.width/this.canvas.height),lookAt(this.eye,target))
    gl.clearColor(.008,.019,.045,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT)
    gl.disable(gl.DEPTH_TEST)
    gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE)
    this.drawTrack(this.stars,[.62,.77,1],.65,gl.POINTS,1.8)
    gl.disable(gl.BLEND);gl.enable(gl.DEPTH_TEST)

    if(this.tracksEnabled&&this.transfer){
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA)
      this.drawTrack(this.earthTrack,[.11,.51,.94],.24,gl.LINE_STRIP)
      this.drawTrack(this.moonTrack,[.76,.83,.95],.24,gl.LINE_STRIP)
      gl.disable(gl.BLEND)
    }
    if(this.showRoute&&this.transfer&&this.route){
      const route=this.route, times=route.times,t=this.current?.t_s??0
      let lo=0,hi=times.length
      while(lo<hi){const mid=(lo+hi)>>1;if(times[mid]<=t)lo=mid+1;else hi=mid}
      const n=Math.max(1,Math.min(times.length,lo))
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA)
      this.drawTrack(route,hexRgb(this.color),.2,gl.POINTS,4)
      this.drawTrack(route,[.37,.52,.69],.26,gl.LINE_STRIP,1,n-1)
      this.drawTrack(route,hexRgb(this.color),.88,gl.LINE_STRIP,1,0,n)
      this.drawTrack(route,hexRgb(this.color),.8,gl.POINTS,3,0,n)
      gl.disable(gl.BLEND)
    }
    const {earth:earthRadius,moon:moonRadius}=this.bodyRadii()
    if(this.sun) {
      // Esfera lejana en dirección JPL, no una posición real del Sol a esta escala.
      // Si la cámara mira al otro lado, la flecha de la interfaz sigue orientando.
      const dir=vNormalize(directionToScene(this.sun.direction_icrf))
      const skySun=vAdd(target,vMul(dir,180))
      this.drawMesh(this.globe,model(skySun,5.7),[1,.8,.25],4)
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE)
      gl.depthMask(false)
      this.drawMesh(this.globe,model(skySun,8),[1,.7,.22],5,.7)
      gl.depthMask(true);gl.disable(gl.BLEND)
    }
    this.updateSunArrow()
    if(earth){
      const rotation=(this.date.getTime()/86164000%1)*Math.PI*2
      this.drawMesh(this.globe,model(earth,earthRadius,rotation),[1,1,1],0)
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE)
      gl.depthMask(false)
      this.drawMesh(this.globe,model(earth,earthRadius*1.10),[.1,.5,.95],3,.33)
      gl.depthMask(true);gl.disable(gl.BLEND)
    }
    if(moon){this.drawMesh(this.globe,model(moon,moonRadius),[1,1,1],1)}
    if(ship&&this.showRoute&&this.current&&this.transfer){
      const speed=toScene(this.current.velocity_m_s,this.transfer.basis_icrf)
      // Mantener el centro exacto y limitar el volumen de la malla para que no
      // se meta visualmente dentro de la Luna/Tierra al aproximarse.
      const gapMoon=moon?vLength(vSub(ship,moon))-moonRadius:Infinity
      const gapEarth=earth?vLength(vSub(ship,earth))-earthRadius:Infinity
      const shipScale=shipScaleForClearance(Math.min(gapMoon,gapEarth),.115)
      if(shipScale>0){
        const shipM=rocketModel(ship,speed,shipScale)
        this.drawMesh(this.rocket[0],shipM,[.88,.94,1.0],2)
        this.drawMesh(this.rocket[1],shipM,[.98,.43,.22],2)
        this.drawMesh(this.rocket[2],shipM,[.15,.86,.93],2)
        gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE)
        this.drawMesh(this.rocket[3],shipM,[.11,.75,1.0],2,.85)
        gl.disable(gl.BLEND)
      }
      // Marcador de píxeles pequeños independiente del zoom: posición real
      // sin inflar una nave que eclipsaría el satélite al realizar la órbita.
      gl.bindBuffer(gl.ARRAY_BUFFER,this.shipPoint.buffer)
      gl.bufferSubData(gl.ARRAY_BUFFER,0,new Float32Array(ship))
      this.drawTrack(this.shipPoint,[.62,1,.85],.98,gl.POINTS,4.5)
    }
    this.updateLabels()
  }
  private frame=()=>{
    if(!this.active)return
    if(!document.hidden) {this.render()}
    this.raf=requestAnimationFrame(this.frame)
  }
  dispose(){
    this.active=false;cancelAnimationFrame(this.raf)
    this.resizeObserver.disconnect();for(const cleanup of this.cleanups)cleanup()
    const gl=this.gl
    for(const t of [this.stars,this.shipPoint,this.earthTrack,this.moonTrack,this.route])if(t)gl.deleteBuffer(t.buffer)
    for(const m of [this.globe,...this.rocket]){gl.deleteBuffer(m.vertices);gl.deleteBuffer(m.indices)}
    gl.deleteProgram(this.meshProgram);gl.deleteProgram(this.dotProgram)
    for(const label of Object.values(this.labels))if(label)label.style.display='none'
  }
}

/** Sistema solar 3D basado en los elementos orbitales medios JPL de esta rama.
 * Cuando se reproduce una misión marciana, Tierra, Marte y nave se sustituyen por
 * posiciones NASA/JPL Horizons del backend, convertidas a eclíptica J2000.
 * La compresión radial afecta SOLO a la representación, no a la física. */
export class SolarSpaceRenderer {
  private gl:WebGLRenderingContext
  private shader:WebGLProgram
  private dots:WebGLProgram
  private globe:Mesh
  private stars:Track
  private guide:Track|null=null
  private route:Path|null=null
  private shipMarker:Track
  private rocket:Mesh[]
  private ship:Vector3|null=null
  private shipVelocity:Vector3=[0,1,0]
  private mission:TransferResponse|null=null
  private showMission=true
  private routeColor:Vector3=[.38,.93,.81]
  private missionTime=0
  private shipLabel:HTMLElement|null=null
  private resizeObserver:ResizeObserver
  private raf=0
  private active=true
  private camera={yaw:-.62,pitch:.42,distance:167,target:[0,0,0] as Vector3}
  private vp:Mat4=new Float32Array(16)
  private eye:Vector3=[0,0,167]
  private date=new Date()
  private positions:Record<string,Vector3>={}
  private pointer:{x:number;y:number;button:number;target:Vector3}|null=null
  private cleanups:(()=>void)[]=[]
  private bodies:Record<string,{kind:number;color:Vector3;radius:number}> = {
    sun:{kind:4,color:[1,.7,.3],radius:4},
    mercury:{kind:6,color:[.7,.7,.68],radius:.6},
    venus:{kind:6,color:[.93,.75,.5],radius:1.1},
    earth:{kind:0,color:[.9,1,1],radius:1.3},
    moon:{kind:1,color:[.75,.79,.84],radius:.66},
    mars:{kind:6,color:[.95,.36,.20],radius:1},
    jupiter:{kind:6,color:[.82,.61,.47],radius:2.3},
    saturn:{kind:6,color:[.9,.79,.59],radius:2},
    uranus:{kind:6,color:[.51,.9,.92],radius:1.35},
    neptune:{kind:6,color:[.35,.5,.94],radius:1.3},
  }
  private canvas:HTMLCanvasElement
  private labels:Record<string,HTMLElement|null>
  constructor(canvas:HTMLCanvasElement, labels:Record<string,HTMLElement|null>, shipLabel:HTMLElement|null=null){
    this.canvas=canvas;this.labels=labels;this.shipLabel=shipLabel
    const gl=canvas.getContext('webgl',{antialias:true,alpha:false,powerPreference:'high-performance'})
    if(!gl)throw new Error('WebGL no disponible en el navegador. Puedes usar la vista 2D.')
    this.gl=gl;this.shader=program(gl,VERTEX_SHADER,FRAGMENT_SHADER)
    this.dots=program(gl,DOT_VERTEX,DOT_FRAGMENT)
    this.globe=sphere(gl);this.stars=createStars(gl);this.rocket=rocketParts(gl)
    this.shipMarker=createTrack(gl,[[0,0,0]])
    gl.bindBuffer(gl.ARRAY_BUFFER,this.shipMarker.buffer);gl.bufferData(gl.ARRAY_BUFFER,12,gl.DYNAMIC_DRAW)
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL)
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas)
    const on=(name:string,cb:EventListener,opts?:AddEventListenerOptions)=>{
      canvas.addEventListener(name,cb,opts);this.cleanups.push(()=>canvas.removeEventListener(name,cb,opts))
    }
    on('pointerdown',((e:PointerEvent)=>{
      if(e.button!==0&&e.button!==2)return
      this.pointer={x:e.clientX,y:e.clientY,button:e.button,target:[...this.camera.target]}
      canvas.setPointerCapture(e.pointerId)
    }) as EventListener)
    on('pointermove',((e:PointerEvent)=>{
      const drag=this.pointer;if(!drag)return
      const dx=e.clientX-drag.x,dy=e.clientY-drag.y
      if(drag.button===0){
        this.camera.yaw-=dx*.007;this.camera.pitch=Math.max(-1.4,Math.min(1.4,this.camera.pitch-dy*.007))
        drag.x=e.clientX;drag.y=e.clientY
      }else{
        const {yaw,pitch,distance}=this.camera
        const right:Vector3=[Math.cos(yaw),0,-Math.sin(yaw)]
        const up:Vector3=[-Math.sin(pitch)*Math.sin(yaw),Math.cos(pitch),-Math.sin(pitch)*Math.cos(yaw)]
        const factor=distance*.0016
        this.camera.target=vAdd(drag.target,vAdd(vMul(right,-dx*factor),vMul(up,dy*factor)))
      }
    }) as EventListener)
    const done=()=>{this.pointer=null}
    on('pointerup',done as EventListener);on('pointercancel',done as EventListener)
    on('lostpointercapture',done as EventListener)
    on('wheel',((e:WheelEvent)=>{e.preventDefault();this.zoom(Math.exp(Math.sign(e.deltaY)*.14))}) as EventListener,{passive:false})
    on('contextmenu',((e:MouseEvent)=>e.preventDefault()) as EventListener)
    this.resize();this.frame()
  }
  /** 1 AU=14959.8 unidades originales: compresión radial creciente y monótona. */
  static position(relativeICRF:Vector3):Vector3 {
    const radius=vLength(relativeICRF),rAU=radius/14959.78707
    return radius>1e-10?vMul(relativeICRF,(22*Math.log1p(2*rAU))/radius):[0,0,0]
  }
  /** Todos los vectores entran en eclíptica heliocéntrica J2000, en metros. */
  setBodies(bodies:Record<string,readonly number[]>|null,date:Date){
    this.date=date
    if(!bodies){this.positions={};return}
    const positions:Record<string,Vector3>={sun:[0,0,0]}
    for(const [id,v] of Object.entries(bodies)) {
      if(!this.bodies[id] || id==='sun')continue
      positions[id]=SolarSpaceRenderer.position(toScene(v))
    }
    // Mostrar satélite solo si existe una posición lunar heliocéntrica real.
    // Al comprimir radialmente el sistema exterior, se separa con un desplazamiento visual explícito.
    if(positions.earth && bodies.earth && bodies.moon) {
      const direction=vNormalize(vSub(toScene(bodies.moon),toScene(bodies.earth)))
      positions.moon=vAdd(positions.earth,vMul(direction,2.7))
    }
    this.positions=positions
    // Líneas radiales informativas, no representan órbitas calculadas.
    const points:Vector3[]=[]
    for(const [id,p] of Object.entries(positions)) if(id!=='sun'&&id!=='moon') points.push([0,0,0],p)
    if(this.guide?.count === points.length){
      this.gl.bindBuffer(this.gl.ARRAY_BUFFER,this.guide.buffer)
      this.gl.bufferData(this.gl.ARRAY_BUFFER,new Float32Array(points.flat()),this.gl.DYNAMIC_DRAW)
    }else{
      if(this.guide)this.gl.deleteBuffer(this.guide.buffer)
      this.guide=points.length?createTrack(this.gl,points):null
    }
  }
  /** Convertir vectores devueltos por el backend (marco orbital → ICRF → eclíptica). */
  private missionPoint(position:readonly number[], sun:readonly number[], basis:number[][]):Vector3 {
    const relative=[position[0]-sun[0],position[1]-sun[1],position[2]-sun[2]]
    return SolarSpaceRenderer.position(toScene(icrfToEcliptic(frameToIcrf(relative,basis))))
  }
  setMission(transfer:TransferResponse|null,color:string,visible:boolean) {
    this.showMission=visible;this.routeColor=hexRgb(color)
    if(this.mission===transfer)return
    this.mission=transfer
    if(this.route)this.gl.deleteBuffer(this.route.buffer)
    this.route=null;this.ship=null
    if(transfer?.destination!=='mars')return
    const positions:Vector3[]=[],times:number[]=[]
    for(const s of transfer.samples){
      if(!s.body_positions_m.sun)continue
      positions.push(this.missionPoint(s.position_m,s.body_positions_m.sun,transfer.basis_icrf))
      times.push(s.t_s)
    }
    if(positions.length>1){
      this.route={...createTrack(this.gl,positions),times:new Float64Array(times)}
      this.home()
    }
  }
  setFrame(state:TransferState|null) {
    this.missionTime=state?.t_s??0
    if(!state || !state.sun_m || !this.mission || this.mission.destination!=='mars'){
      this.ship=null;return
    }
    this.ship=this.missionPoint(state.position_m,state.sun_m,this.mission.basis_icrf)
    // Diferencia visual local para orientar el cohete. No son velocidades físicas calculadas.
    const p=state.position_m,v=state.velocity_m_s,dt=3600
    this.shipVelocity=vSub(this.missionPoint(vAdd(p,vMul(v,dt)),state.sun_m,this.mission.basis_icrf),this.ship)
  }
  zoom(factor:number){this.camera.distance=Math.max(4,Math.min(1000,this.camera.distance*factor))}
  home(){this.camera={yaw:-.62,pitch:.42,distance:this.mission?.destination==='mars'?78:167,target:[0,0,0]}}
  focus(id:string){const p=this.positions[id];if(p){this.camera.target=[...p];this.camera.distance=id==='sun'?20:14}}
  private resize(){const rect=this.canvas.getBoundingClientRect();if(!rect.width||!rect.height)return
    const pixel=Math.min(window.devicePixelRatio||1,1.75),limit=Math.min(1,1900/Math.max(rect.width*pixel,rect.height*pixel))
    const w=Math.round(rect.width*pixel*limit),h=Math.round(rect.height*pixel*limit)
    if(this.canvas.width!==w||this.canvas.height!==h){this.canvas.width=w;this.canvas.height=h}
    this.gl.viewport(0,0,w,h)
  }
  private drawMesh(position:Vector3,radius:number,color:Vector3,kind:number){
    const gl=this.gl,p=this.shader
    gl.useProgram(p);gl.bindBuffer(gl.ARRAY_BUFFER,this.globe.vertices)
    const pos=gl.getAttribLocation(p,'aPosition'),norm=gl.getAttribLocation(p,'aNormal')
    gl.enableVertexAttribArray(pos);gl.enableVertexAttribArray(norm)
    gl.vertexAttribPointer(pos,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(norm,3,gl.FLOAT,false,24,12)
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,this.globe.indices)
    gl.uniformMatrix4fv(gl.getUniformLocation(p,'uVP'),false,this.vp)
    gl.uniformMatrix4fv(gl.getUniformLocation(p,'uModel'),false,model(position,radius))
    gl.uniform3fv(gl.getUniformLocation(p,'uCamera'),this.eye)
    const light=vNormalize(vMul(position,-1))
    gl.uniform3fv(gl.getUniformLocation(p,'uSun'),kind===4?[.8,.4,.6]:light)
    gl.uniform3fv(gl.getUniformLocation(p,'uColor'),color)
    gl.uniform1f(gl.getUniformLocation(p,'uKind'),kind)
    gl.uniform1f(gl.getUniformLocation(p,'uAlpha'),1)
    gl.uniform1f(gl.getUniformLocation(p,'uTime'),this.date.getTime()/1000)
    gl.drawElements(gl.TRIANGLES,this.globe.length,gl.UNSIGNED_SHORT,0)
  }
  private drawDots(t:Track,rgb:Vector3,alpha:number,size:number,mode:number,start=0,count?:number){
    const gl=this.gl,p=this.dots;gl.useProgram(p)
    const attr=gl.getAttribLocation(p,'aPosition')
    gl.bindBuffer(gl.ARRAY_BUFFER,t.buffer);gl.enableVertexAttribArray(attr)
    gl.vertexAttribPointer(attr,3,gl.FLOAT,false,0,0)
    gl.uniformMatrix4fv(gl.getUniformLocation(p,'uVP'),false,this.vp)
    gl.uniform3fv(gl.getUniformLocation(p,'uColor'),rgb)
    gl.uniform1f(gl.getUniformLocation(p,'uAlpha'),alpha)
    gl.uniform1f(gl.getUniformLocation(p,'uSize'),size)
    gl.uniform1f(gl.getUniformLocation(p,'uPoints'),mode===gl.POINTS?1:0)
    gl.drawArrays(mode,start,count??t.count)
  }
  private drawShip() {
    if(!this.ship || !this.showMission)return
    const gl=this.gl,p=this.shader,ship=this.ship
    const gap=Math.min(...['earth','mars'].map(id=>this.positions[id]
      ?vLength(vSub(ship,this.positions[id]))-this.bodies[id].radius:Infinity))
    const scale=shipScaleForClearance(gap,.16)
    if(scale>0){
      const m=rocketModel(ship,this.shipVelocity,scale)
      const colors:Vector3[]=[[.86,.94,1],[.98,.46,.25],[.21,.87,.93],[.19,.73,1]]
      for(let i=0;i<this.rocket.length;i++){
        const mesh=this.rocket[i]
        gl.useProgram(p);gl.bindBuffer(gl.ARRAY_BUFFER,mesh.vertices)
        const pos=gl.getAttribLocation(p,'aPosition'),norm=gl.getAttribLocation(p,'aNormal')
        gl.enableVertexAttribArray(pos);gl.enableVertexAttribArray(norm)
        gl.vertexAttribPointer(pos,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(norm,3,gl.FLOAT,false,24,12)
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,mesh.indices)
        gl.uniformMatrix4fv(gl.getUniformLocation(p,'uVP'),false,this.vp)
        gl.uniformMatrix4fv(gl.getUniformLocation(p,'uModel'),false,m)
        gl.uniform3fv(gl.getUniformLocation(p,'uCamera'),this.eye)
        gl.uniform3fv(gl.getUniformLocation(p,'uSun'),vNormalize(vMul(ship,-1)))
        gl.uniform3fv(gl.getUniformLocation(p,'uColor'),colors[i])
        gl.uniform1f(gl.getUniformLocation(p,'uKind'),2)
        gl.uniform1f(gl.getUniformLocation(p,'uAlpha'),1)
        gl.uniform1f(gl.getUniformLocation(p,'uTime'),this.date.getTime()/1000)
        gl.drawElements(gl.TRIANGLES,mesh.length,gl.UNSIGNED_SHORT,0)
      }
    }
    gl.bindBuffer(gl.ARRAY_BUFFER,this.shipMarker.buffer)
    gl.bufferSubData(gl.ARRAY_BUFFER,0,new Float32Array(ship))
    this.drawDots(this.shipMarker,[.5,1,.85],.95,5,gl.POINTS)
  }
  private frame=()=>{if(!this.active)return
    if(!document.hidden)this.render()
    this.raf=requestAnimationFrame(this.frame)
  }
  private render(){const gl=this.gl;if(!this.canvas.height)return
    const {yaw,pitch,distance,target}=this.camera
    const offset:Vector3=[distance*Math.cos(pitch)*Math.sin(yaw),distance*Math.sin(pitch),distance*Math.cos(pitch)*Math.cos(yaw)]
    this.eye=vAdd(target,offset)
    this.vp=multiply(perspective(this.canvas.width/this.canvas.height),lookAt(this.eye,target))
    gl.clearColor(.008,.017,.039,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT)
    gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE)
    this.drawDots(this.stars,[.63,.77,1],.64,1.9,gl.POINTS)
    if(this.guide){gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);this.drawDots(this.guide,[.36,.55,.76],.22,1,gl.LINES)}
    if(this.route && this.showMission){
      gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA)
      this.drawDots(this.route,this.routeColor,.20,1,gl.LINE_STRIP)
      const times=this.route.times
      let lo=0,hi=times.length
      while(lo<hi){const mid=(lo+hi)>>1;if(times[mid]<=this.missionTime)lo=mid+1;else hi=mid}
      if(lo>1)this.drawDots(this.route,this.routeColor,.96,2,gl.LINE_STRIP,0,lo)
    }
    gl.disable(gl.BLEND);gl.enable(gl.DEPTH_TEST)
    for(const [id,p] of Object.entries(this.positions)){
      const b=this.bodies[id];this.drawMesh(p,b.radius,b.color,b.kind)
      const el=this.labels[id];if(!el)continue
      const m=this.vp
      const x=m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12]
      const y=m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13]
      const z=m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14]
      const w=m[3]*p[0]+m[7]*p[1]+m[11]*p[2]+m[15]
      const px=(x/w*.5+.5)*this.canvas.clientWidth,py=(-y/w*.5+.5)*this.canvas.clientHeight
      const visible=w>0&&z/w<1&&px>=0&&px<=this.canvas.clientWidth&&py>=0&&py<=this.canvas.clientHeight
      el.style.display=visible?'block':'none';if(visible){el.style.left=`${px}px`;el.style.top=`${py+24}px`}
    }
    for(const [id,el] of Object.entries(this.labels))if(el&&!this.positions[id])el.style.display='none'
    this.drawShip()
    if(this.shipLabel){
      const p=this.ship,el=this.shipLabel,m=this.vp
      if(!p||!this.showMission){el.style.display='none'}
      else {
        const x=m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12]
        const y=m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13]
        const z=m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14]
        const w=m[3]*p[0]+m[7]*p[1]+m[11]*p[2]+m[15]
        const px=(x/w*.5+.5)*this.canvas.clientWidth,py=(-y/w*.5+.5)*this.canvas.clientHeight
        const valid=w>0&&z/w<1&&px>=0&&px<=this.canvas.clientWidth&&py>=0&&py<=this.canvas.clientHeight
        el.style.display=valid?'block':'none';if(valid){el.style.left=`${px}px`;el.style.top=`${py-20}px`}
      }
    }
  }
  dispose(){this.active=false;cancelAnimationFrame(this.raf);this.resizeObserver.disconnect()
    for(const clean of this.cleanups)clean()
    const gl=this.gl;gl.deleteBuffer(this.stars.buffer);gl.deleteBuffer(this.shipMarker.buffer);if(this.guide)gl.deleteBuffer(this.guide.buffer);if(this.route)gl.deleteBuffer(this.route.buffer)
    for(const m of [this.globe,...this.rocket]){gl.deleteBuffer(m.vertices);gl.deleteBuffer(m.indices)}
    gl.deleteProgram(this.shader);gl.deleteProgram(this.dots)
    for(const label of [...Object.values(this.labels),this.shipLabel])if(label)label.style.display='none'
  }
}
