// =====================================================================
// Ecotroca — geolocalização e distâncias
// Não depende do Google Maps: funciona mesmo sem o mapa carregado.
// =====================================================================

const RAIO_TERRA_KM = 6371;

/** Distância em km entre dois pontos {lat, lng} pela fórmula de Haversine. */
export function distanciaKm(a, b) {
  const rad = (graus) => (graus * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * RAIO_TERRA_KM * Math.asin(Math.sqrt(h));
}

const formatoKm = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const formatoKmInteiro = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });

/** Ex.: 0,35 → "350 m"; 1,234 → "1,2 km"; 23,4 → "23 km". */
export function formatarDistancia(km) {
  if (!Number.isFinite(km)) return '';
  if (km < 1) return `${Math.max(10, Math.round((km * 1000) / 10) * 10)} m`;
  if (km < 10) return `${formatoKm.format(km)} km`;
  return `${formatoKmInteiro.format(km)} km`;
}

/** Link de rota do Google Maps até o ponto (abre o app ou o site, sem precisar de chave). */
export function urlComoChegar(lat, lng) {
  // Number() garante que só números entram na URL
  return `https://www.google.com/maps/dir/?api=1&destination=${Number(lat)},${Number(lng)}`;
}

export const geolocalizacaoDisponivel = () => 'geolocation' in navigator;

/** Promessa com a posição atual do usuário: {lat, lng, precisao}. */
export function obterPosicao() {
  return new Promise((resolve, reject) => {
    if (!geolocalizacaoDisponivel()) {
      reject(Object.assign(new Error('sem suporte'), { code: 'SEM_SUPORTE' }));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, precisao: pos.coords.accuracy }),
      (erro) => reject(erro),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 }
    );
  });
}

/** Mensagem amigável para cada tipo de erro de geolocalização. */
export function mensagemErroPosicao(erro) {
  switch (erro && erro.code) {
    case 1: // PERMISSION_DENIED
      return 'Você não permitiu o acesso à localização. Tudo bem: mostramos os pontos de Sorocaba/SP. Para ver o mais próximo, libere a localização nas configurações do navegador.';
    case 2: // POSITION_UNAVAILABLE
      return 'Não conseguimos descobrir sua localização agora. Mostramos os pontos de Sorocaba/SP.';
    case 3: // TIMEOUT
      return 'A localização demorou demais para responder. Tente de novo em um lugar com melhor sinal.';
    case 'SEM_SUPORTE':
      return 'Seu navegador não informa a localização. Mostramos os pontos de Sorocaba/SP.';
    default:
      return 'Algo deu errado ao buscar sua localização. Mostramos os pontos de Sorocaba/SP.';
  }
}

/** Estado atual da permissão ('granted' | 'denied' | 'prompt' | 'desconhecido'). */
export async function estadoPermissao() {
  try {
    if (!navigator.permissions) return 'desconhecido';
    const status = await navigator.permissions.query({ name: 'geolocation' });
    return status.state;
  } catch {
    return 'desconhecido';
  }
}
