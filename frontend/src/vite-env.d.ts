/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_SIMULATION_PATH?: string
  readonly VITE_EPHEMERIDES_PATH?: string
}
interface ImportMeta { readonly env: ImportMetaEnv }
