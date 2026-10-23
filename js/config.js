// =====================================================================
// Ecotroca — configuração
// Todos os valores aqui são PÚBLICOS (vão para o navegador).
// Nunca coloque a chave "service_role" do Supabase neste arquivo.
// Enquanto um valor começar com "COLE_", ele é tratado como não configurado.
// =====================================================================

// Supabase: Project Settings → API (URL do projeto e chave pública anon/publishable)
export const SUPABASE_URL = 'https://uqgqyqehykkxlnrnoxml.supabase.co';
export const SUPABASE_ANON_KEY = 'sb_publishable_C8DJGlZlEpwJIot8J9vnPA_yOCpOIKj';

// Google Maps JavaScript API (restrinja a chave por HTTP referrer — veja o README)
export const GOOGLE_MAPS_API_KEY = 'COLE_AQUI_A_CHAVE_DO_GOOGLE_MAPS';
// Map ID (necessário para marcadores avançados). "DEMO_MAP_ID" funciona para testes;
// para produção, crie um Map ID no Google Cloud (Map Management) e cole aqui.
export const GOOGLE_MAPS_MAP_ID = 'DEMO_MAP_ID';

// Link do Google Forms de feedback. Enquanto for placeholder, o botão fica oculto.
export const FEEDBACK_FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSdOtf4Ovx7FxaVon2iBD1EKzEhrWQzS3q2Yaie1gTWmwUmgMg/viewform';

// Região padrão do mapa: Sorocaba/SP
export const CENTRO_PADRAO = { lat: -23.5015, lng: -47.4526 };
export const ZOOM_PADRAO = 13;

/** true quando o valor ainda não foi preenchido. */
export function naoConfigurado(valor) {
  return !valor || typeof valor !== 'string' || valor.trim() === '' || valor.startsWith('COLE_');
}
