// =====================================================================
// Ecotroca — página principal
// Liga dados (data.js), localização (geo.js) e mapa (map.js) à interface.
// Todo texto vindo do banco entra no HTML via textContent (nunca innerHTML).
// =====================================================================

import { FEEDBACK_FORM_URL, GOOGLE_MAPS_API_KEY, naoConfigurado } from './config.js';
import { carregarPontos } from './data.js';
import {
  distanciaKm,
  formatarDistancia,
  obterPosicao,
  mensagemErroPosicao,
  estadoPermissao,
  urlComoChegar,
} from './geo.js';
import { iniciarMapa } from './map.js';

document.documentElement.classList.add('js');

// Tipos de resíduo usados nos filtros (mesmos nomes do banco)
const CATEGORIAS = [
  'Celulares',
  'Pilhas e baterias',
  'Cabos e carregadores',
  'Computadores e periféricos',
  'Eletrodomésticos pequenos',
];
const TODOS = 'Todos';
const DISTANCIA_FORA_DA_AREA_KM = 60;

// ---------- Estado da página ----------
const estado = {
  pontos: [],
  carregado: false,
  filtro: TODOS,
  usuario: null,       // { lat, lng }
  distancias: new Map(), // id → km
  proximoId: null,
  selecionadoId: null,
  mapa: null,          // controlador devolvido por iniciarMapa()
};

// ---------- Elementos ----------
const $ = (seletor) => document.querySelector(seletor);
const el = {
  lista: $('#lista-pontos'),
  contagem: $('#lista-contagem'),
  filtros: $('#filtros'),
  status: $('#status-localizacao'),
  botaoLocalizar: $('#botao-localizacao'),
  avisoDemo: $('#aviso-demo'),
  mapa: $('#mapa-google'),
};

/** Cria elemento com classe e texto seguro. */
function criar(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto != null) no.textContent = texto;
  return no;
}

const normalizarTexto = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const desktop = () => window.matchMedia('(min-width: 900px)').matches;

// =====================================================================
// Lista de pontos
// =====================================================================

/** Pontos que passam no filtro, ordenados por distância (ou por nome). */
function pontosVisiveis() {
  const alvo = normalizarTexto(estado.filtro);
  const filtrados =
    estado.filtro === TODOS
      ? [...estado.pontos]
      : estado.pontos.filter((p) => p.residuos.some((r) => normalizarTexto(r) === alvo));
  if (estado.usuario) {
    filtrados.sort((a, b) => estado.distancias.get(a.id) - estado.distancias.get(b.id));
  } else {
    filtrados.sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR', { numeric: true }));
  }
  return filtrados;
}

/** Bloco de detalhes de um ponto (horário, resíduos, telefone, status, rota). */
function criarDetalhes(ponto, idDetalhes) {
  const detalhes = criar('div', 'ponto__detalhes');
  detalhes.id = idDetalhes;
  const dados = criar('dl', 'ponto__dados');

  const linha = (rotulo, conteudo) => {
    const grupo = document.createElement('div');
    grupo.append(criar('dt', null, rotulo));
    const dd = document.createElement('dd');
    dd.append(conteudo);
    grupo.append(dd);
    dados.append(grupo);
  };

  linha('Horário', ponto.horario || 'Não informado. Confirme com o local.');

  if (ponto.residuos.length) {
    const ul = criar('ul', 'ponto__residuos');
    ponto.residuos.forEach((r) => ul.append(criar('li', null, r)));
    linha('Resíduos aceitos', ul);
  } else {
    linha('Resíduos aceitos', 'Não informado. Confirme com o local.');
  }

  if (ponto.telefone) {
    const tel = criar('a', null, ponto.telefone);
    tel.href = `tel:${ponto.telefone.replace(/[^\d+]/g, '')}`;
    linha('Telefone', tel);
  }

  const info = document.createDocumentFragment();
  info.append(
    criar(
      'span',
      `status ${ponto.verificado ? 'status--verificado' : 'status--pendente'}`,
      ponto.verificado ? 'Verificado' : 'Em verificação'
    )
  );
  info.append(criar('span', 'status__fonte', `Fonte: ${ponto.fonte || 'não informada'}`));
  linha('Informação', info);

  const rota = criar('a', 'botao', 'Como chegar');
  rota.href = urlComoChegar(ponto.lat, ponto.lng);
  rota.target = '_blank';
  rota.rel = 'noopener';
  rota.setAttribute('aria-label', `Como chegar a ${ponto.nome} (abre o Google Maps)`);

  detalhes.append(dados, rota);
  return detalhes;
}

/** Item da lista: cabeçalho clicável + detalhes recolhíveis. */
function criarItem(ponto) {
  const item = criar('li', 'ponto');
  item.dataset.id = ponto.id;
  const idDetalhes = `detalhes-${ponto.id}`;
  const proximo = ponto.id === estado.proximoId;
  if (proximo) item.classList.add('is-proximo');

  const cabeca = criar('button', 'ponto__cabeca');
  cabeca.type = 'button';
  cabeca.setAttribute('aria-expanded', 'false');
  cabeca.setAttribute('aria-controls', idDetalhes);

  if (proximo) {
    const selos = criar('span', 'ponto__selos');
    selos.append(criar('span', 'selo selo--proximo', 'Mais próximo'));
    cabeca.append(selos);
  }
  cabeca.append(criar('span', 'ponto__nome', ponto.nome));
  const km = estado.distancias.get(ponto.id);
  if (estado.usuario && Number.isFinite(km)) {
    const dist = criar('span', 'ponto__distancia', formatarDistancia(km));
    dist.setAttribute('aria-label', `a ${formatarDistancia(km)}`);
    cabeca.append(dist);
  }
  cabeca.append(criar('span', 'ponto__endereco', ponto.endereco));
  cabeca.addEventListener('click', () => selecionar(estado.selecionadoId === ponto.id ? null : ponto.id, 'lista'));

  const detalhes = criarDetalhes(ponto, idDetalhes);
  detalhes.hidden = true;
  item.append(cabeca, detalhes);
  return item;
}

/** Mensagem de estado dentro da lista (carregando, erro, vazio). */
function mostrarEstadoLista(texto, { tentarDeNovo = false } = {}) {
  const li = criar('li', 'lista__estado', texto);
  if (tentarDeNovo) {
    const botao = criar('button', 'botao', 'Tentar de novo');
    botao.type = 'button';
    botao.addEventListener('click', carregarDados);
    li.append(document.createElement('br'), botao);
  }
  el.lista.replaceChildren(li);
}

/** Redesenha lista, contagem e marcadores conforme filtro e localização. */
function renderizar() {
  const visiveis = pontosVisiveis();
  estado.proximoId = estado.usuario && visiveis.length ? visiveis[0].id : null;
  if (estado.selecionadoId && !visiveis.some((p) => p.id === estado.selecionadoId)) estado.selecionadoId = null;

  el.lista.setAttribute('aria-busy', 'false');
  if (!estado.pontos.length) {
    mostrarEstadoLista('Ainda não há pontos de coleta cadastrados. Volte em breve.');
    el.contagem.textContent = '';
  } else if (!visiveis.length) {
    mostrarEstadoLista('Nenhum ponto aceita esse tipo de resíduo por enquanto. Tente outro filtro.');
    el.contagem.textContent = 'Nenhum ponto encontrado';
  } else {
    el.lista.replaceChildren(...visiveis.map(criarItem));
    const n = visiveis.length;
    el.contagem.textContent = `${n} ${n === 1 ? 'ponto' : 'pontos'}${estado.usuario ? ', do mais perto ao mais longe' : ''}`;
  }

  if (estado.mapa) {
    estado.mapa.filtrar(new Set(visiveis.map((p) => p.id)));
    estado.mapa.marcarProximo(estado.proximoId);
  }
  aplicarSelecao({ mover: false });
}

/** Abre/fecha os detalhes na lista e sincroniza o mapa. */
function aplicarSelecao({ mover = true, origem } = {}) {
  for (const item of el.lista.querySelectorAll('.ponto')) {
    const aberto = item.dataset.id === estado.selecionadoId;
    item.querySelector('.ponto__cabeca').setAttribute('aria-expanded', String(aberto));
    item.querySelector('.ponto__detalhes').hidden = !aberto;
    if (aberto && origem === 'mapa' && desktop()) item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  if (estado.mapa) {
    estado.mapa.selecionar(estado.selecionadoId, {
      distanciaKm: estado.distancias.get(estado.selecionadoId),
      mover,
    });
  }
}

function selecionar(id, origem) {
  estado.selecionadoId = id;
  aplicarSelecao({ origem });
}

// =====================================================================
// Filtros
// =====================================================================

function montarFiltros() {
  const extras = new Set();
  for (const p of estado.pontos) {
    for (const r of p.residuos) {
      if (!CATEGORIAS.some((c) => normalizarTexto(c) === normalizarTexto(r))) extras.add(r);
    }
  }
  const opcoes = [TODOS, ...CATEGORIAS, ...[...extras].sort((a, b) => a.localeCompare(b, 'pt-BR'))];
  el.filtros.replaceChildren(
    ...opcoes.map((opcao) => {
      const botao = criar('button', 'filtro', opcao);
      botao.type = 'button';
      botao.setAttribute('aria-pressed', String(opcao === estado.filtro));
      botao.addEventListener('click', () => {
        estado.filtro = opcao;
        el.filtros.querySelectorAll('.filtro').forEach((b) => b.setAttribute('aria-pressed', String(b === botao)));
        renderizar();
        if (estado.usuario) anunciarProximo({ enquadrar: true });
      });
      return botao;
    })
  );
}

// =====================================================================
// Localização
// =====================================================================

function definirStatus(conteudo, { erro = false } = {}) {
  el.status.classList.toggle('is-erro', erro);
  el.status.replaceChildren(...(Array.isArray(conteudo) ? conteudo : [conteudo]));
}

/** Escreve no status qual é o ponto mais próximo e, se pedido, enquadra o mapa. */
function anunciarProximo({ enquadrar = false } = {}) {
  const proximo = estado.pontos.find((p) => p.id === estado.proximoId);
  if (!proximo) {
    definirStatus('Localização encontrada, mas não há pontos para esse filtro.');
    return;
  }
  const km = estado.distancias.get(proximo.id);
  const partes = [
    'Mais próximo: ',
    criar('strong', null, proximo.nome),
    ` — ${proximo.endereco} (${formatarDistancia(km)}).`,
  ];
  if (km > DISTANCIA_FORA_DA_AREA_KM) partes.push(' Por enquanto, a Ecotroca mostra pontos de Sorocaba/SP.');
  definirStatus(partes);

  estado.selecionadoId = proximo.id;
  aplicarSelecao({ mover: false });
  if (enquadrar && estado.mapa) estado.mapa.enquadrar(estado.usuario, proximo);
}

let localizando = false;

async function localizar() {
  if (localizando) return;
  localizando = true;
  const rotulo = el.botaoLocalizar.querySelector('span');
  el.botaoLocalizar.setAttribute('aria-busy', 'true');
  rotulo.textContent = 'Localizando…';
  definirStatus('Buscando sua localização…');

  try {
    const posicao = await obterPosicao();
    estado.usuario = { lat: posicao.lat, lng: posicao.lng };
    estado.distancias = new Map(estado.pontos.map((p) => [p.id, distanciaKm(estado.usuario, p)]));
    if (estado.mapa) estado.mapa.definirUsuario(estado.usuario);
    if (estado.carregado) {
      renderizar();
      anunciarProximo({ enquadrar: true });
    } else {
      definirStatus('Localização encontrada. Carregando os pontos…');
    }
    rotulo.textContent = 'Atualizar localização';
  } catch (erro) {
    definirStatus(mensagemErroPosicao(erro), { erro: true });
    if (estado.mapa) estado.mapa.centralizarPadrao();
    rotulo.textContent = 'Usar minha localização';
  } finally {
    el.botaoLocalizar.removeAttribute('aria-busy');
    localizando = false;
  }
}

// =====================================================================
// Carregamento de dados e mapa
// =====================================================================

async function carregarDados() {
  el.lista.setAttribute('aria-busy', 'true');
  mostrarEstadoLista('Carregando pontos de coleta…');
  el.contagem.textContent = '';
  try {
    const { pontos, demonstracao } = await carregarPontos();
    estado.pontos = pontos;
    estado.carregado = true;
    el.avisoDemo.hidden = !demonstracao;
    if (estado.usuario) estado.distancias = new Map(pontos.map((p) => [p.id, distanciaKm(estado.usuario, p)]));
    montarFiltros();
    if (estado.mapa) estado.mapa.definirPontos(pontos);
    renderizar();
    if (estado.usuario) anunciarProximo({ enquadrar: true });
  } catch (erro) {
    console.error('[Ecotroca] Erro ao carregar pontos:', erro);
    el.lista.setAttribute('aria-busy', 'false');
    mostrarEstadoLista('Não foi possível carregar os pontos de coleta agora. Verifique sua conexão.', { tentarDeNovo: true });
  }
}

/** Mensagem no lugar do mapa (conteúdo fixo, escrito por nós). */
function avisoNoMapa(titulo, texto) {
  const aviso = criar('div', 'mapa__aviso');
  aviso.append(criar('strong', null, titulo), criar('span', null, texto));
  el.mapa.replaceChildren(aviso);
}

async function carregarMapa() {
  if (naoConfigurado(GOOGLE_MAPS_API_KEY)) {
    avisoNoMapa(
      'O mapa ainda não está ativo.',
      'Falta configurar a chave da API do Google Maps no arquivo js/config.js. A lista de pontos continua funcionando, inclusive com a sua localização.'
    );
    return;
  }
  let falhou = false;
  try {
    const controlador = await iniciarMapa(el.mapa, {
      aoClicarPonto: (id) => selecionar(id, 'mapa'),
      aoFalhar: () => {
        falhou = true;
        estado.mapa = null;
        avisoNoMapa(
          'Não foi possível exibir o mapa.',
          'A chave do Google Maps foi recusada (verifique a chave e as restrições de domínio). A lista de pontos continua funcionando.'
        );
      },
    });
    if (falhou) return; // a chave foi recusada enquanto o mapa iniciava
    estado.mapa = controlador;
    if (estado.carregado) {
      estado.mapa.definirPontos(estado.pontos);
      renderizar();
    }
    if (estado.usuario) {
      estado.mapa.definirUsuario(estado.usuario);
      if (estado.carregado) anunciarProximo({ enquadrar: true });
    }
  } catch (erro) {
    console.error('[Ecotroca] Erro ao carregar o mapa:', erro);
    estado.mapa = null;
    avisoNoMapa('Não foi possível carregar o mapa agora.', 'Verifique sua conexão. A lista de pontos continua funcionando.');
  }
}

// =====================================================================
// Interface geral: menu, feedback, animações
// =====================================================================

function iniciarMenu() {
  const botao = $('.topo__menu');
  const menu = $('#menu-principal');
  const fechar = () => {
    menu.classList.remove('is-aberto');
    botao.setAttribute('aria-expanded', 'false');
  };
  botao.addEventListener('click', () => {
    const abrir = !menu.classList.contains('is-aberto');
    menu.classList.toggle('is-aberto', abrir);
    botao.setAttribute('aria-expanded', String(abrir));
  });
  menu.addEventListener('click', (e) => {
    if (e.target.closest('a')) fechar();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && menu.classList.contains('is-aberto')) {
      fechar();
      botao.focus();
    }
  });

  const topo = $('.topo');
  const marcarRolagem = () => topo.classList.toggle('is-rolado', window.scrollY > 8);
  window.addEventListener('scroll', marcarRolagem, { passive: true });
  marcarRolagem();
}

function iniciarFeedback() {
  const url = FEEDBACK_FORM_URL;
  if (naoConfigurado(url) || !/^https:\/\//i.test(url)) return; // placeholder: botão fica oculto
  document.querySelectorAll('[data-feedback-link]').forEach((a) => (a.href = url));
  document.querySelectorAll('[data-feedback]').forEach((bloco) => (bloco.hidden = false));
}

function iniciarAnimacoes() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) return;
  const alvos = document.querySelectorAll('.passos, .descarte, .duvidas, .sobre');
  const observador = new IntersectionObserver(
    (entradas) => {
      for (const entrada of entradas) {
        if (entrada.isIntersecting) {
          entrada.target.classList.add('is-visivel');
          observador.unobserve(entrada.target);
        }
      }
    },
    { threshold: 0.08 }
  );
  alvos.forEach((alvo) => {
    alvo.classList.add('revelar');
    observador.observe(alvo);
  });
}

// =====================================================================
// Início
// =====================================================================

function iniciar() {
  iniciarMenu();
  iniciarFeedback();
  iniciarAnimacoes();

  el.botaoLocalizar.addEventListener('click', localizar);
  // "Encontrar ponto de coleta": o link rola até o mapa e já pede a localização
  document.querySelectorAll('[data-acao="localizar"]').forEach((link) => link.addEventListener('click', localizar));

  carregarDados();
  carregarMapa();

  // Se a pessoa já permitiu a localização antes, localiza sem precisar clicar
  estadoPermissao().then((estadoAtual) => {
    if (estadoAtual === 'granted') localizar();
  });
}

iniciar();
