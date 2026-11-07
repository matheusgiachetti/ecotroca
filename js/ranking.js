// =====================================================================
// Ecotroca — seção Ranking
// Top 10 por período (semana, mês, geral) e por cidade. Só mostra apelido, cidade e
// pontos de quem pontuou (a soma e a ordem vêm do banco). Todo texto do banco entra por
// textContent. Quem está logado e fora do top 10 vê a própria posição abaixo da lista.
// js/conta.js avisa quando a sessão muda ('ecotroca:sessao') e quando os pontos mudam
// ('ecotroca:pontos').
// =====================================================================

import { ranking, minhaPosicao, meuPerfil, modoDemonstracao, LIMITE_RANKING } from './data.js';

const TEXTO_DO_PERIODO = { semana: 'nesta semana', mes: 'neste mês', geral: 'no geral' };

const $ = (seletor, raiz = document) => raiz.querySelector(seletor);

function criar(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto != null) no.textContent = texto;
  return no;
}

const formatoNumero = new Intl.NumberFormat('pt-BR');
const pontosPorExtenso = (n) => `${formatoNumero.format(n)} ${n === 1 ? 'ponto' : 'pontos'}`;
const posicaoPorExtenso = (n) => `${formatoNumero.format(n)}º`;

export function iniciarRanking() {
  const secao = $('#ranking');
  if (!secao) return;
  if (modoDemonstracao()) {
    // Sem Supabase não há ranking: some a seção e o link do menu
    secao.hidden = true;
    const itemMenu = $('[data-ranking-nav]');
    if (itemMenu) itemMenu.hidden = true;
    return;
  }

  const lista = $('#ranking-lista');
  const contagem = $('#ranking-contagem');
  const minhaEl = $('#ranking-minha');
  const botoesPeriodo = [...secao.querySelectorAll('[data-periodo]')];
  const botoesCidade = [...secao.querySelectorAll('[data-cidade]')];
  const botaoMinhaCidade = $('[data-cidade="minha"]', secao);

  const estado = { periodo: 'semana', cidade: 'todas', logado: false, perfil: null };
  let pedido = 0; // descarta respostas antigas quando o filtro muda no meio de uma busca

  const cidadeDoFiltro = () => (estado.cidade === 'minha' && estado.perfil ? estado.perfil.cidade : null);

  function marcarBotoes() {
    for (const b of botoesPeriodo) b.setAttribute('aria-pressed', String(b.dataset.periodo === estado.periodo));
    for (const b of botoesCidade) b.setAttribute('aria-pressed', String(b.dataset.cidade === estado.cidade));
    // "Minha cidade" só existe para quem está logado e tem cidade preenchida
    botaoMinhaCidade.hidden = !(estado.logado && estado.perfil && estado.perfil.cidade);
  }

  function mostrarEstado(texto, { tentarDeNovo = false } = {}) {
    const li = criar('li', 'lista__estado', texto);
    if (tentarDeNovo) {
      const botao = criar('button', 'botao botao--suave', 'Tentar de novo');
      botao.type = 'button';
      botao.addEventListener('click', carregar);
      li.append(document.createElement('br'), botao);
    }
    lista.replaceChildren(li);
  }

  function textoDaContagem(n, cidade) {
    const onde = cidade ? `, em ${cidade}` : '';
    const quando = TEXTO_DO_PERIODO[estado.periodo];
    if (n === 0) return `Nenhuma pessoa no ranking ${quando}${onde}.`;
    if (n >= LIMITE_RANKING) return `As ${n} primeiras posições ${quando}${onde}.`;
    return `${n} ${n === 1 ? 'pessoa pontuou' : 'pessoas pontuaram'} ${quando}${onde}.`;
  }

  function criarLinha(linha) {
    const item = criar('li', 'rank');
    if (linha.posicao <= 3) item.classList.add(`rank--${linha.posicao}`);
    const ehVoce = !!(estado.perfil && estado.perfil.apelido === linha.apelido);
    if (ehVoce) item.classList.add('rank--voce');

    const nome = criar('span', 'rank__nome', linha.apelido);
    if (ehVoce) nome.append(' ', criar('span', 'rank__voce', 'Você'));
    item.append(
      criar('span', 'rank__pos', posicaoPorExtenso(linha.posicao)),
      nome,
      criar('span', 'rank__cidade', linha.cidade),
      criar('span', 'rank__pontos', pontosPorExtenso(linha.pontos))
    );
    return item;
  }

  function desenhar(linhas, minha) {
    lista.setAttribute('aria-busy', 'false');
    const cidade = cidadeDoFiltro();
    contagem.textContent = textoDaContagem(linhas.length, cidade);
    if (!linhas.length) mostrarEstado('Ninguém pontuou ainda neste período.');
    else lista.replaceChildren(...linhas.map(criarLinha));

    // Minha posição, separada, só quando a pessoa está fora do top
    minhaEl.replaceChildren();
    minhaEl.hidden = true;
    if (!estado.logado || minha === undefined) return;
    if (minha === null) {
      minhaEl.append(criar('p', 'rank__aviso', 'Você ainda não pontuou neste período.'));
    } else if (minha.posicao > LIMITE_RANKING) {
      minhaEl.append(
        criar('p', 'rank__rotulo', 'Sua posição'),
        criar('p', 'rank__minha-linha', `${posicaoPorExtenso(minha.posicao)}, com ${pontosPorExtenso(minha.pontos)}`)
      );
    } else {
      return; // já aparece destacada na lista
    }
    minhaEl.hidden = false;
  }

  async function carregar() {
    const meu = ++pedido;
    const cidade = cidadeDoFiltro();
    marcarBotoes();
    lista.setAttribute('aria-busy', 'true');
    mostrarEstado('Carregando o ranking…');
    contagem.textContent = '';
    minhaEl.hidden = true;
    try {
      const [linhas, minha] = await Promise.all([
        ranking(estado.periodo, cidade, LIMITE_RANKING),
        // Se a posição falhar, o ranking público continua aparecendo
        estado.logado ? minhaPosicao(estado.periodo, cidade).catch(() => undefined) : undefined,
      ]);
      if (meu !== pedido) return;
      desenhar(linhas, minha);
    } catch (erro) {
      if (meu !== pedido) return;
      console.error('[Ecotroca] Erro ao carregar o ranking:', erro);
      lista.setAttribute('aria-busy', 'false');
      contagem.textContent = '';
      mostrarEstado('Não foi possível carregar o ranking agora. Verifique sua conexão.', { tentarDeNovo: true });
    }
  }

  // ---------- Filtros ----------
  for (const botao of botoesPeriodo) {
    botao.addEventListener('click', () => {
      estado.periodo = botao.dataset.periodo;
      carregar();
    });
  }
  for (const botao of botoesCidade) {
    botao.addEventListener('click', () => {
      estado.cidade = botao.dataset.cidade;
      carregar();
    });
  }

  // ---------- Conta ----------
  document.addEventListener('ecotroca:sessao', async (e) => {
    const logado = !!(e.detail && e.detail.logado);
    if (logado === estado.logado) return; // nada mudou
    estado.logado = logado;
    estado.perfil = null;
    if (logado) {
      try {
        estado.perfil = await meuPerfil();
      } catch {
        estado.perfil = null;
      }
    } else if (estado.cidade === 'minha') {
      estado.cidade = 'todas';
    }
    carregar();
  });
  document.addEventListener('ecotroca:pontos', carregar);

  marcarBotoes();
  carregar();
}
