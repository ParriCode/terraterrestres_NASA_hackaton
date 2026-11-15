// Minimal Node ESM loader so `node --test` can import .ts sources (Node 20 lacks type stripping).
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

export async function resolve(specifier, context, next) {
  try { return await next(specifier, context) } catch (err) {
    if (specifier.startsWith('.') && !/\.\w+$/.test(specifier)) return next(`${specifier}.ts`, context)
    throw err
  }
}

export async function load(url, context, next) {
  if (!url.endsWith('.ts')) return next(url, context)
  const source = await readFile(new URL(url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, verbatimModuleSyntax: false },
    fileName: url,
  })
  return { format: 'module', source: outputText, shortCircuit: true }
}
