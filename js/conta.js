// =====================================================================
// Ecotroca — interface da conta e do registro de descarte
// Dois painéis (<dialog> no index.html): conta (entrar, criar conta, minha
// conta) e descarte. Usa só as funções de data.js; as regras (200 m, limites,
// pontos) vivem no banco. Todo texto dinâmico entra por textContent.
// Esc fecha o painel e o foco volta para quem o abriu.
// =====================================================================

import {
  cadastrar,
  entrar,
  sair,
  sessaoAtual,
  listarTiposResiduo,
  registrarDescarte,
  meuResumo,
  modoDemonstracao,
} from './data.js';
import { obterPosicao } from './geo.js';

// Mesmos limites do banco (nivel_por_pontos em supabase/05-rpc-pontos.sql), só para a barra de progresso.
// O NOME do nível vem sempre do banco.
const NIVEIS = [
  { nome: 'Semente', de: 0 },
  { nome: 'Broto', de: 50 },
  { nome: 'Muda', de: 150 },
  { nome: 'Árvore', de: 350 },
  { nome: 'Floresta', de: 700 },
];

const $ = (seletor, raiz = document) => raiz.querySelector(seletor);

function criar(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto != null) no.textContent = texto;
  return no;
}

const formatoNumero = new Intl.NumberFormat('pt-BR');
const pontosPorExtenso = (n) => `${formatoNumero.format(n)} ${n === 1 ? 'ponto' : 'pontos'}`;
const formatarKg = (kg) =>
  `${new Intl.NumberFormat('pt-BR', { maximumFractionDigits: kg < 1 ? 3 : 2 }).format(kg)} kg`;

/** Mensagem para cada falha de localização ao registrar um descarte. */
function mensagemPosicao(erro) {
  switch (erro && erro.code) {
    case 1:
      return 'Para registrar o descarte, o site precisa da sua localização. Libere o acesso nas configurações do navegador e tente de novo.';
    case 2:
      return 'Não conseguimos descobrir sua localização agora. Tente de novo em um lugar com melhor sinal.';
    case 3:
      return 'A localização demorou demais para responder. Tente de novo em um lugar com melhor sinal.';
    case 'SEM_SUPORTE':
      return 'Seu navegador não informa a localização, então não dá para registrar o descarte por aqui.';
    default:
      return 'Não foi possível obter a sua localização. Tente de novo.';
  }
}

/**
 * Liga os painéis. Devolve { disponivel, registrarDescarteDe(ponto, botao) }.
 * Sem Supabase configurado (modo demonstração) não há conta: o menu esconde o botão.
 */
export function iniciarConta() {
  const itemMenu = $('[data-conta]');
  if (modoDemonstracao()) {
    if (itemMenu) itemMenu.hidden = true;
    return { disponivel: false, registrarDescarteDe() {} };
  }

  // ---------- Elementos ----------
  const botaoConta = $('[data-conta-abrir]');
  const botaoSair = $('[data-conta-sair]');
  const botaoMenu = $('.topo__menu');
  const anuncio = $('#anuncio');

  const dlgConta = $('#painel-conta');
  const tituloConta = $('#conta-titulo');
  const sobreConta = $('#conta-sobretitulo');
  const avisoConta = $('#conta-aviso');
  const formEntrar = $('#form-entrar');
  const formCriar = $('#form-criar');
  const resumoEl = {
    nivel: $('#resumo-nivel'),
    barra: $('#resumo-barra'),
    proximo: $('#resumo-proximo'),
    pontos: $('#resumo-pontos'),
    descartes: $('#resumo-descartes'),
    itens: $('#resumo-itens'),
    kg: $('#resumo-kg'),
    erro: $('#resumo-erro'),
  };

  const dlgDescarte = $('#painel-descarte');
  const tituloDescarte = $('#painel-descarte-titulo');
  const formDescarte = $('#form-descarte');
  const tiposEl = $('#descarte-tipos');
  const quantidadeEl = $('#descarte-quantidade');
  const previaEl = $('#descarte-previa');
  const erroDescarte = $('#descarte-erro');
  const statusDescarte = $('#descarte-status');
  const botaoConfirmar = $('#descarte-confirmar');
  const resultadoEl = $('#descarte-resultado');

  // ---------- Estado ----------
  let sessao = null;
  let pendente = null; // descarte que espera o login: { ponto, opener, fallback }
  let tipos = null; // tipos de resíduo, lidos uma vez
  let pontoAtual = null;
  const aberturas = new Map(); // painel -> { opener, fallback } (para devolver o foco)

  const apelidoDe = (s) => (s && s.user && s.user.user_metadata && s.user.user_metadata.apelido) || 'Minha conta';
  const anunciar = (texto) => {
    anuncio.textContent = texto;
  };

  // ---------- Painéis: abrir, focar, fechar, devolver o foco ----------
  function fecharMenuMobile() {
    if (botaoMenu.getAttribute('aria-expanded') === 'true') botaoMenu.click();
  }

  function focarInicial(dlg) {
    const titulo = $('[tabindex="-1"]', dlg);
    const campo = dlg.dataset.foco === 'titulo' ? null : $('form:not([hidden]) input', dlg);
    (campo || titulo).focus();
  }

  function abrirDialog(dlg, opener, fallback) {
    if (dlg.open) return;
    aberturas.set(dlg, { opener, fallback });
    fecharMenuMobile();
    dlg.showModal();
    focarInicial(dlg);
  }

  const visivel = (el) => !!el && el.isConnected && el.getClientRects().length > 0;

  for (const dlg of [dlgConta, dlgDescarte]) {
    dlg.addEventListener('close', () => {
      if ($('dialog[open]')) return; // outro painel assumiu (ex.: login → descarte)
      if (dlg === dlgConta) pendente = null; // fechou sem entrar: o descarte pendente cai
      const { opener, fallback } = aberturas.get(dlg) || {};
      aberturas.delete(dlg);
      const alvo = [opener, fallback && fallback(), botaoConta, botaoMenu].find(visivel);
      if (alvo) alvo.focus();
    });
    // Clique fora do conteúdo (no fundo escurecido) fecha
    dlg.addEventListener('click', (e) => {
      if (e.target === dlg) dlg.close();
    });
    dlg.addEventListener('click', (e) => {
      if (e.target.closest('[data-fechar]')) dlg.close();
    });
  }

  function ocupar(botao, rotulo) {
    botao.dataset.rotulo = botao.textContent;
    botao.textContent = rotulo;
    botao.setAttribute('aria-busy', 'true');
  }
  function liberar(botao) {
    botao.textContent = botao.dataset.rotulo;
    botao.removeAttribute('aria-busy');
  }
  const ocupado = (botao) => botao.getAttribute('aria-busy') === 'true';

  // ---------- Menu ----------
  function atualizarMenu() {
    if (sessao) {
      botaoConta.replaceChildren(criar('span', 'sr-only', 'Minha conta: '), document.createTextNode(apelidoDe(sessao)));
      botaoSair.hidden = false;
    } else {
      botaoConta.textContent = 'Entrar';
      botaoSair.hidden = true;
    }
  }

  // ---------- Painel da conta ----------
  const avisoDoDescarte = () => (pendente ? `Entre para registrar o descarte em ${pendente.ponto.nome}.` : '');

  function mostrarVista(vista, aviso = avisoDoDescarte()) {
    for (const parte of dlgConta.querySelectorAll('[data-vista]')) parte.hidden = parte.dataset.vista !== vista;
    tituloConta.textContent = vista === 'entrar' ? 'Entrar' : vista === 'criar' ? 'Criar conta' : apelidoDe(sessao);
    sobreConta.textContent = vista === 'conta' ? 'Minha conta' : 'Conta';
    avisoConta.hidden = !aviso;
    avisoConta.textContent = aviso || '';
    for (const erro of dlgConta.querySelectorAll('.form__erro')) erro.textContent = '';
    if (dlgConta.open) focarInicial(dlgConta);
  }

  function abrirConta(vista, opener, fallback, aviso) {
    mostrarVista(vista, aviso);
    abrirDialog(dlgConta, opener, fallback);
    if (vista === 'conta') carregarResumo();
  }

  for (const botao of dlgConta.querySelectorAll('[data-ir-vista]')) {
    botao.addEventListener('click', () => mostrarVista(botao.dataset.irVista));
  }

  /** Depois de entrar: atualiza o menu, fecha o painel e, se havia um descarte esperando, abre-o. */
  function aposEntrar(novaSessao) {
    sessao = novaSessao;
    atualizarMenu();
    anunciar(`Você entrou como ${apelidoDe(sessao)}.`);
    const espera = pendente;
    pendente = null;
    dlgConta.close();
    if (espera) abrirDescarte(espera.ponto, espera.opener, espera.fallback);
  }

  async function enviarForm(form, rotuloOcupado, acao) {
    const botao = $('button[type="submit"]', form);
    const erroEl = $('.form__erro', form);
    if (ocupado(botao)) return;
    erroEl.textContent = '';
    ocupar(botao, rotuloOcupado);
    try {
      await acao(form.elements);
      form.reset();
    } catch (erro) {
      erroEl.textContent = erro.message || 'Algo deu errado. Tente de novo.';
    } finally {
      liberar(botao);
    }
  }

  formEntrar.addEventListener('submit', (e) => {
    e.preventDefault();
    enviarForm(formEntrar, 'Entrando…', async (campos) => {
      const { sessao: nova } = await entrar(campos.email.value, campos.senha.value);
      aposEntrar(nova);
    });
  });

  formCriar.addEventListener('submit', (e) => {
    e.preventDefault();
    enviarForm(formCriar, 'Criando a conta…', async (campos) => {
      const email = campos.email.value.trim();
      const resultado = await cadastrar(email, campos.senha.value, campos.apelido.value);
      if (resultado.precisaConfirmar) {
        const aviso = `Enviamos um e-mail para ${email}. Abra a mensagem e confirme o cadastro para entrar.`;
        mostrarVista('entrar', aviso);
        anunciar(aviso);
      } else {
        aposEntrar(resultado.sessao);
      }
    });
  });

  async function fazerSair() {
    const veioDoMenu = document.activeElement === botaoSair;
    try {
      await sair();
    } catch (erro) {
      anunciar(erro.message);
      return;
    }
    sessao = null;
    atualizarMenu();
    anunciar('Você saiu da conta.');
    if (dlgConta.open) dlgConta.close(); // o foco volta sozinho para quem abriu o painel
    else if (veioDoMenu) (visivel(botaoConta) ? botaoConta : botaoMenu).focus(); // o botão "Sair" sumiu
  }
  botaoSair.addEventListener('click', fazerSair);
  $('[data-conta-sair-painel]').addEventListener('click', fazerSair);

  botaoConta.addEventListener('click', () => abrirConta(sessao ? 'conta' : 'entrar', botaoConta));

  // ---------- Minha conta ----------
  function nivelDe(resumo) {
    const indice = NIVEIS.findIndex((n) => n.nome === resumo.nivel);
    return indice >= 0 ? indice : 0;
  }

  async function carregarResumo() {
    resumoEl.erro.textContent = '';
    resumoEl.nivel.textContent = '—';
    resumoEl.proximo.textContent = 'Carregando…';
    resumoEl.barra.max = 1;
    resumoEl.barra.value = 0;
    for (const campo of ['pontos', 'descartes', 'itens', 'kg']) resumoEl[campo].textContent = '—';
    try {
      const r = await meuResumo();
      const atual = NIVEIS[nivelDe(r)];
      const proximo = NIVEIS[nivelDe(r) + 1];
      resumoEl.nivel.textContent = r.nivel;
      if (proximo) {
        resumoEl.barra.max = proximo.de - atual.de;
        resumoEl.barra.value = Math.min(Math.max(r.pontosTotal - atual.de, 0), proximo.de - atual.de);
        resumoEl.proximo.textContent = `Faltam ${pontosPorExtenso(proximo.de - r.pontosTotal)} para o nível ${proximo.nome}.`;
      } else {
        resumoEl.barra.max = 1;
        resumoEl.barra.value = 1;
        resumoEl.proximo.textContent = 'Você chegou ao nível mais alto.';
      }
      resumoEl.pontos.textContent = formatoNumero.format(r.pontosTotal);
      resumoEl.descartes.textContent = formatoNumero.format(r.descartes);
      resumoEl.itens.textContent = formatoNumero.format(r.itens);
      resumoEl.kg.textContent = `${formatarKg(r.kgEstimados)} (estimativa)`;
    } catch (erro) {
      resumoEl.proximo.textContent = '';
      resumoEl.erro.textContent = erro.message;
      if (erro.codigo === 'nao_logado') sessaoExpirou();
    }
  }

  /** A sessão acabou: volta para o menu sem conta e pede o login de novo. */
  function sessaoExpirou(opener, fallback) {
    sessao = null;
    atualizarMenu();
    if (dlgDescarte.open) dlgDescarte.close();
    abrirConta('entrar', opener, fallback, 'Sua sessão acabou. Entre de novo para continuar.');
  }

  // ---------- Registrar descarte ----------
  function resetarDescarte() {
    formDescarte.hidden = false;
    resultadoEl.hidden = true;
    quantidadeEl.value = '1';
    erroDescarte.textContent = '';
    statusDescarte.textContent = '';
    previaEl.textContent = '';
  }

  function atualizarPrevia() {
    const escolhido = $('input[name="tipo"]:checked', formDescarte);
    const quantidade = Number(quantidadeEl.value);
    const tipo = escolhido && tipos && tipos.find((t) => String(t.id) === escolhido.value);
    previaEl.textContent =
      tipo && Number.isInteger(quantidade) && quantidade >= 1 && quantidade <= 10
        ? `Esse descarte vale ${pontosPorExtenso(tipo.pontos * quantidade)}.`
        : '';
  }
  formDescarte.addEventListener('input', atualizarPrevia);

  function montarTipos() {
    tiposEl.setAttribute('aria-busy', 'false');
    tiposEl.replaceChildren(
      ...tipos.map((tipo) => {
        const rotulo = criar('label', 'opcao');
        const radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'tipo';
        radio.value = String(tipo.id);
        rotulo.append(
          radio,
          criar('span', 'opcao__marca'),
          criar('span', 'opcao__nome', tipo.nome),
          criar('span', 'opcao__pontos', `${pontosPorExtenso(tipo.pontos)} por item`)
        );
        return rotulo;
      })
    );
  }

  async function carregarTipos() {
    if (tipos) {
      montarTipos();
      return;
    }
    tiposEl.setAttribute('aria-busy', 'true');
    tiposEl.replaceChildren(criar('p', 'lista__estado', 'Carregando os tipos de resíduo…'));
    try {
      tipos = await listarTiposResiduo();
      montarTipos();
    } catch (erro) {
      tiposEl.setAttribute('aria-busy', 'false');
      const tentar = criar('button', 'botao botao--suave', 'Tentar de novo');
      tentar.type = 'button';
      tentar.addEventListener('click', carregarTipos);
      tiposEl.replaceChildren(criar('p', 'lista__estado', erro.message), tentar);
    }
  }

  function abrirDescarte(ponto, opener, fallback) {
    const volta = fallback || (() => $(`.ponto[data-id="${CSS.escape(ponto.id)}"] .ponto__cabeca`));
    if (!sessao) {
      pendente = { ponto, opener, fallback: volta };
      abrirConta('entrar', opener, volta);
      return;
    }
    pontoAtual = ponto;
    tituloDescarte.textContent = ponto.nome;
    resetarDescarte();
    abrirDialog(dlgDescarte, opener, volta);
    carregarTipos();
  }

  formDescarte.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (ocupado(botaoConfirmar)) return;
    erroDescarte.textContent = '';
    statusDescarte.textContent = '';

    const escolhido = $('input[name="tipo"]:checked', formDescarte);
    const quantidade = Number(quantidadeEl.value);
    if (!escolhido) {
      erroDescarte.textContent = 'Escolha o tipo de resíduo.';
      return;
    }
    if (!Number.isInteger(quantidade) || quantidade < 1 || quantidade > 10) {
      erroDescarte.textContent = 'A quantidade deve ser de 1 a 10 itens.';
      return;
    }

    ocupar(botaoConfirmar, 'Confirmando…');
    try {
      // Só agora, depois do clique em "Confirmar", o site pede a localização.
      statusDescarte.textContent = 'Buscando a sua localização…';
      let posicao;
      try {
        posicao = await obterPosicao();
      } catch (erro) {
        erroDescarte.textContent = mensagemPosicao(erro);
        return;
      }

      statusDescarte.textContent = 'Registrando o descarte…';
      try {
        const r = await registrarDescarte(pontoAtual.id, Number(escolhido.value), quantidade, posicao.lat, posicao.lng);
        $('#descarte-resultado-texto').textContent =
          `+${pontosPorExtenso(r.pontosGanhos)}. Você agora tem ${pontosPorExtenso(r.pontosTotal)}, nível ${r.nivel}.`;
        $('#descarte-resultado-peso').textContent = `Peso estimado deste descarte: ${formatarKg(r.pesoKgEstimado)} (estimativa).`;
        formDescarte.hidden = true;
        resultadoEl.hidden = false;
        anunciar(`Descarte registrado. ${$('#descarte-resultado-texto').textContent}`);
        $('#descarte-outro').focus();
      } catch (erro) {
        if (erro.codigo === 'nao_logado') {
          const espera = { ponto: pontoAtual, ...(aberturas.get(dlgDescarte) || {}) };
          pendente = { ponto: espera.ponto, opener: espera.opener, fallback: espera.fallback };
          sessaoExpirou(espera.opener, espera.fallback);
        } else {
          erroDescarte.textContent = erro.message;
        }
      }
    } finally {
      statusDescarte.textContent = '';
      liberar(botaoConfirmar);
    }
  });

  $('#descarte-outro').addEventListener('click', () => {
    resetarDescarte();
    carregarTipos();
    focarInicial(dlgDescarte);
  });

  // ---------- Início ----------
  sessaoAtual().then((s) => {
    sessao = s;
    atualizarMenu();
  });

  return { disponivel: true, registrarDescarteDe: abrirDescarte };
}
