#!/usr/bin/env bash
# Despliegue de ORBITAL 4B en producción (monza:/srv/nasa).
#
#   /srv/nasa/front     → frontend YA COMPILADO (npm run build, estáticos)
#   /srv/nasa/backend   → backend YA EMPAQUETADO (wheel .whl) + su entorno .venv
#
# Root no puede entrar por SSH: se entra como jlpf, se sube el paquete a /tmp con scp y
# después se hace root (su, o sudo con --become sudo) UNA vez para instalar y arrancar.
#
# Uso:
#   ./deploy.sh                          # jlpf@monza (SSH 2020), front 3000, backend 3001, parxiom.es, su
#   ./deploy.sh jlpf@monza --frontend-port 3000 --backend-port 3001 --ssh-port 2020 --public-host parxiom.es --become sudo
#
# El front lo sirve nginx en el puerto del front y pasa /api/ al backend (ver sites-available/nasa).
set -euo pipefail

TARGET=jlpf@monza
[[ $# -gt 0 && "$1" != -* ]] && { TARGET="$1"; shift; }
REMOTE_DIR=/srv/nasa
BACKEND_PORT=3001
FRONTEND_PORT=3000
SSH_PORT=2020
PUBLIC_HOST=parxiom.es
BECOME=su
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)  BACKEND_PORT="$2"; shift 2 ;;
    --frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
    --ssh-port)      SSH_PORT="$2"; shift 2 ;;
    --public-host)   PUBLIC_HOST="$2"; shift 2 ;;
    --dir)           REMOTE_DIR="$2"; shift 2 ;;
    --become)        BECOME="$2"; shift 2 ;;
    *) echo "Opción desconocida: $1"; exit 1 ;;
  esac
done
[[ "$BECOME" == su || "$BECOME" == sudo ]] || { echo "--become debe ser su o sudo"; exit 1; }

ROOT="$(cd "$(dirname "$0")" && pwd)"
# Una sola conexión SSH reutilizada por ssh y scp: la clave/contraseña de jlpf se pide una vez.
CTL="/tmp/orbital4b-deploy-%r@%h:%p"
CTL_OPTS=(-o ControlMaster=auto -o ControlPath="$CTL" -o ControlPersist=300 -o ConnectTimeout=15)
SSH=(ssh -p "$SSH_PORT" "${CTL_OPTS[@]}" "$TARGET")
SCP=(scp -P "$SSH_PORT" "${CTL_OPTS[@]}")
trap 'ssh -O exit -o ControlPath="$CTL" -p "$SSH_PORT" "$TARGET" 2>/dev/null || true' EXIT
# nginx (puerto del front) sirve los estáticos y pasa /api/ al backend local: misma URL, sin CORS.
# nginx (443, HTTPS) sirve los estáticos y pasa /api/ al backend local: misma URL, sin CORS.
API_URL="https://$PUBLIC_HOST/api"
WEB_URL="https://$PUBLIC_HOST"
BUILD="$ROOT/.deploy-build"
STAGE=/tmp/orbital4b-deploy   # carpeta temporal de jlpf en el servidor

echo "==> Rama: $(git -C "$ROOT" branch --show-current)  ($(git -C "$ROOT" log -1 --format='%h %s'))"
rm -rf "$BUILD"; mkdir -p "$BUILD/pkg/front" "$BUILD/pkg/wheels"

echo "==> 1/4 Compilando frontend (API = $API_URL)"
( cd "$ROOT/frontend" && npm ci --silent && VITE_API_BASE_URL="$API_URL" npm run build )
cp -r "$ROOT/frontend/dist/." "$BUILD/pkg/front/"

echo "==> 2/4 Empaquetando backend (wheel)"
( cd "$ROOT/backend" && rm -rf build ./*.egg-info \
  && python3 -m pip wheel . --no-deps -q -w "$BUILD/pkg/wheels" && rm -rf build ./*.egg-info )
WHEEL="$(basename "$(ls "$BUILD"/pkg/wheels/*.whl)")"
echo "    $WHEEL"
tar -czf "$BUILD/orbital4b.tar.gz" -C "$BUILD/pkg" .
echo "    paquete: $(du -h "$BUILD/orbital4b.tar.gz" | cut -f1)"

# Script que se ejecutará como root en el servidor.
cat > "$BUILD/install.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
# Debian mínimo: instalar lo que falte (python3, venv/ensurepip, curl). Solo la primera vez.
need=()
command -v python3 >/dev/null || need+=(python3)
python3 -c 'import ensurepip, venv' 2>/dev/null || need+=("python3-venv" "python3-pip")
command -v curl >/dev/null || need+=(curl)
if [ \${#need[@]} -gt 0 ]; then
  echo "    instalando paquetes del sistema: \${need[*]}"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq && apt-get install -y -qq "\${need[@]}" >/dev/null
fi
mkdir -p '$REMOTE_DIR/front' '$REMOTE_DIR/backend/wheels'
cd '$REMOTE_DIR'
echo '    descomprimiendo'
rm -rf front && mkdir -p front
rm -rf '$STAGE/pkg' && mkdir -p '$STAGE/pkg'
tar -xzf '$STAGE/orbital4b.tar.gz' -C '$STAGE/pkg'
cp -r '$STAGE/pkg/front/.' front/
cp '$STAGE/pkg/wheels/'*.whl backend/wheels/

echo '    instalando backend'
cd backend
# Un intento fallido puede dejar un .venv sin pip: en ese caso se recrea.
[ -x .venv/bin/pip ] || { rm -rf .venv; python3 -m venv .venv; }
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q --force-reinstall --no-deps 'wheels/$WHEEL'
.venv/bin/pip install -q 'wheels/$WHEEL'
cd ..

echo '    reiniciando servicios'
for name in backend front; do   # front.pid: restos del despliegue antiguo con http.server
  [ -f \$name.pid ] && kill \$(cat \$name.pid) 2>/dev/null || true
  rm -f \$name.pid
done
sleep 1
# Backend sin --reload. setsid: siguen vivos al cerrar la sesión de root/SSH.
( cd backend && ORBITAL_CORS_ORIGINS='$WEB_URL' ORBITAL_HORIZONS_CACHE='$REMOTE_DIR/backend/.cache/horizons.sqlite3' \\
  setsid nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $BACKEND_PORT \\
  > ../backend.log 2>&1 < /dev/null & echo \$! > ../backend.pid )
sleep 4
curl -fsS http://127.0.0.1:$BACKEND_PORT/health >/dev/null && echo '    backend OK' || { echo 'Backend NO arranca:'; tail -30 backend.log; exit 1; }
# El front lo sirve nginx (sites-available/nasa, listen $FRONTEND_PORT).
if curl -fsSk --resolve '$PUBLIC_HOST:443:127.0.0.1' https://$PUBLIC_HOST/api/health >/dev/null; then echo '    nginx OK (https + /api)'
else echo '    AVISO: nginx no sirve /api/ en https://$PUBLIC_HOST. Revisa /etc/nginx/sites-enabled/nasa.'; fi
rm -rf '$STAGE'
EOF

echo "==> 3/4 Subiendo con scp a $TARGET:$STAGE"
"${SSH[@]}" "rm -rf '$STAGE' && mkdir -p '$STAGE'"
"${SCP[@]}" "$BUILD/orbital4b.tar.gz" "$BUILD/install.sh" "$TARGET:$STAGE/"
rm -rf "$BUILD"

echo "==> 4/4 Instalando y arrancando como root en $REMOTE_DIR ($BECOME: te pedirá la contraseña)"
if [[ "$BECOME" == su ]]; then
  ssh -t -p "$SSH_PORT" "${CTL_OPTS[@]}" "$TARGET" "su -c 'bash $STAGE/install.sh'"
else
  ssh -t -p "$SSH_PORT" "${CTL_OPTS[@]}" "$TARGET" "sudo bash $STAGE/install.sh"
fi

echo
echo "Desplegado en $TARGET:$REMOTE_DIR"
echo "  Front:   $WEB_URL"
echo "  API:     $API_URL   (backend en 127.0.0.1:$BACKEND_PORT, detrás de nginx)"
echo "  Logs:    ssh -p $SSH_PORT $TARGET   →   su -c 'tail -f $REMOTE_DIR/backend.log'"
