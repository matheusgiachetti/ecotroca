// =====================================================================
// Ecotroca — tudo o que depende do Google Maps fica aqui.
// O resto do site só usa o "controlador" devolvido por iniciarMapa(),
// então trocar de provedor de mapas significa reescrever só este arquivo.
// Usa a API atual: importLibrary + AdvancedMarkerElement.
// =====================================================================

import { GOOGLE_MAPS_API_KEY, GOOGLE_MAPS_MAP_ID, CENTRO_PADRAO, ZOOM_PADRAO } from './config.js';
import { formatarDistancia, urlComoChegar } from './geo.js';

const TEMPO_LIMITE_MS = 15000;
const ZOOM_MAXIMO_ENQUADRAR = 16;

/**
 * Carregador oficial do Google Maps (bootstrap de importLibrary),
 * reescrito de forma legível. Instala google.maps.importLibrary sem
 * baixar nada até a primeira chamada.
 */
function instalarCarregador(parametros) {
  const g = (window.google = window.google || {});
  const maps = (g.maps = g.maps || {});
  if (maps.importLibrary) return;

  const bibliotecas = new Set();
  let promessa;

  const carregar = () =>
    promessa ||
    (promessa = new Promise((resolve, reject) => {
      const query = new URLSearchParams();
      query.set('libraries', [...bibliotecas].join(','));
      for (const [chave, valor] of Object.entries(parametros)) {
        query.set(chave.replace(/[A-Z]/g, (l) => '_' + l.toLowerCase()), valor);
      }
      query.set('callback', 'google.maps.__ib__');
      maps.__ib__ = resolve;
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?${query}`;
      script.async = true;
      script.onerror = () => reject(new Error('Não foi possível baixar o Google Maps.'));
      document.head.append(script);
    }));

  maps.importLibrary = (nome, ...resto) => {
    bibliotecas.add(nome);
    return carregar().then(() => maps.importLibrary(nome, ...resto));
  };
}

/** Rejeita a promessa se ela demorar mais que `ms`. */
function comTempoLimite(promessa, ms) {
  return Promise.race([
    promessa,
    new Promise((_, reject) => setTimeout(() => reject(new Error('Tempo esgotado ao carregar o mapa.')), ms)),
  ]);
}

/** Cria um elemento com classe e texto (sempre via textContent: seguro contra HTML do banco). */
function criar(tag, classe, texto) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texto != null) el.textContent = texto;
  return el;
}

/**
 * Inicia o mapa no elemento `container`.
 * @param {HTMLElement} container
 * @param {{ aoClicarPonto: (id: string) => void, aoFalhar: (msg: string) => void }} opcoes
 */
export async function iniciarMapa(container, { aoClicarPonto, aoFalhar }) {
  // Chave inválida / domínio não autorizado: o Google chama esta função global.
  window.gm_authFailure = () => aoFalhar('autenticacao');

  instalarCarregador({ key: GOOGLE_MAPS_API_KEY, v: 'weekly', language: 'pt-BR', region: 'BR' });

  const [{ Map, InfoWindow }, { AdvancedMarkerElement }, { LatLngBounds }] = await comTempoLimite(
    Promise.all([
      google.maps.importLibrary('maps'),
      google.maps.importLibrary('marker'),
      google.maps.importLibrary('core'),
    ]),
    TEMPO_LIMITE_MS
  );

  container.replaceChildren();
  const mapa = new Map(container, {
    center: CENTRO_PADRAO,
    zoom: ZOOM_PADRAO,
    mapId: GOOGLE_MAPS_MAP_ID,
    gestureHandling: 'cooperative',
    streetViewControl: false,
    mapTypeControl: false,
    fullscreenControl: true,
    clickableIcons: false,
  });

  const balao = new InfoWindow({ maxWidth: 280 });
  const marcadores = new globalThis.Map(); // id → { marcador, conteudo, ponto }
  let marcadorUsuario = null;
  let selecionadoId = null;

  /** Monta o conteúdo do balão de um ponto. */
  function conteudoBalao(ponto, distanciaKm) {
    const raiz = criar('div', 'balao');
    raiz.append(criar('p', null, ponto.endereco));
    if (Number.isFinite(distanciaKm)) raiz.append(criar('p', null, `A ${formatarDistancia(distanciaKm)} de você`));
    const link = criar('a', null, 'Como chegar');
    link.href = urlComoChegar(ponto.lat, ponto.lng);
    link.target = '_blank';
    link.rel = 'noopener';
    raiz.append(link);
    return raiz;
  }

  return {
    /** Cria um marcador para cada ponto (substitui os anteriores). */
    definirPontos(pontos) {
      for (const { marcador } of marcadores.values()) marcador.map = null;
      marcadores.clear();
      for (const ponto of pontos) {
        const conteudo = criar('div', 'marcador');
        const marcador = new AdvancedMarkerElement({
          map: mapa,
          position: { lat: ponto.lat, lng: ponto.lng },
          content: conteudo,
          title: ponto.nome,
          gmpClickable: true,
        });
        marcador.addEventListener('gmp-click', () => aoClicarPonto(ponto.id));
        marcadores.set(ponto.id, { marcador, conteudo, ponto });
      }
    },

    /** Mostra só os marcadores cujos ids estão no conjunto. */
    filtrar(idsVisiveis) {
      for (const [id, { marcador }] of marcadores) marcador.map = idsVisiveis.has(id) ? mapa : null;
      if (selecionadoId && !idsVisiveis.has(selecionadoId)) balao.close();
    },

    /** Destaca o ponto mais próximo com o selo "Mais próximo" (ou remove o destaque com null). */
    marcarProximo(idProximo) {
      for (const [id, { marcador, conteudo }] of marcadores) {
        const proximo = id === idProximo;
        conteudo.classList.toggle('is-proximo', proximo);
        conteudo.textContent = proximo ? 'Mais próximo' : '';
        marcador.zIndex = proximo ? 10 : null;
      }
    },

    /** Seleciona um ponto: realça o marcador e abre o balão com nome e endereço. */
    selecionar(id, { distanciaKm, mover = true } = {}) {
      selecionadoId = id;
      for (const [outroId, { conteudo }] of marcadores) conteudo.classList.toggle('is-selecionado', outroId === id);
      const item = id && marcadores.get(id);
      if (!item) {
        balao.close();
        return;
      }
      balao.setOptions({ disableAutoPan: !mover });
      balao.setHeaderContent(criar('strong', 'balao__titulo', item.ponto.nome));
      balao.setContent(conteudoBalao(item.ponto, distanciaKm));
      balao.open({ map: mapa, anchor: item.marcador, shouldFocus: false });
    },

    /** Coloca (ou move) o marcador "Você está aqui". */
    definirUsuario(posicao) {
      if (!marcadorUsuario) {
        const conteudo = criar('div', 'marcador-usuario');
        marcadorUsuario = new AdvancedMarkerElement({ map: mapa, content: conteudo, title: 'Você está aqui', zIndex: 20 });
      }
      marcadorUsuario.position = { lat: posicao.lat, lng: posicao.lng };
    },

    /** Enquadra o usuário e o ponto indicado. */
    enquadrar(posicao, ponto) {
      const limites = new LatLngBounds();
      limites.extend(posicao);
      limites.extend({ lat: ponto.lat, lng: ponto.lng });
      mapa.fitBounds(limites, 72);
      google.maps.event.addListenerOnce(mapa, 'idle', () => {
        if (mapa.getZoom() > ZOOM_MAXIMO_ENQUADRAR) mapa.setZoom(ZOOM_MAXIMO_ENQUADRAR);
      });
    },

    /** Volta para a região padrão (Sorocaba/SP). */
    centralizarPadrao() {
      mapa.setCenter(CENTRO_PADRAO);
      mapa.setZoom(ZOOM_PADRAO);
    },
  };
}
