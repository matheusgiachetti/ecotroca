// =====================================================================
// Ecotroca — regras dos pontos
// Lê regras_pontos() do banco (supabase/07-medalhas.sql) e desenha a seção
// "Como os pontos funcionam". O site NUNCA repete esses números: raio, limites,
// pontos por tipo, níveis e medalhas vêm todos do banco. conta.js usa
// obterRegras() para a barra de nível e os limites do formulário.
// Todo texto vindo do banco entra por textContent.
// =====================================================================

import { regrasPontos, modoDemonstracao } from './data.js';

const $ = (seletor, raiz = document) => raiz.querySelector(seletor);

function criar(tag, classe, texto) {
  const no = document.createElement(tag);
  if (classe) no.className = classe;
  if (texto != null) no.textContent = texto;
  return no;
}

const formatoNumero = new Intl.NumberFormat('pt-BR');
export const pontosPorExtenso = (n) => `${formatoNumero.format(n)} ${n === 1 ? 'ponto' : 'pontos'}`;
const itensPorExtenso = (n) => `${formatoNumero.format(n)} ${n === 1 ? 'item' : 'itens'}`;

// ---------- Cache: uma leitura por visita; falha não fica guardada ----------
let promessa = null;
let ultimas = null;

/** Regras do banco (leitura única). Se falhar, a próxima chamada tenta de novo. */
export function obterRegras() {
  if (!promessa) {
    promessa = regrasPontos().then(
      (regras) => {
        ultimas = regras;
        return regras;
      },
      (erro) => {
        promessa = null;
        throw erro;
      }
    );
  }
  return promessa;
}

/** As regras já lidas, ou null se ainda não carregaram. */
export const regrasCarregadas = () => ultimas;

const nomeDoFuso = (fuso) => (fuso === 'America/Sao_Paulo' ? 'horário de Brasília' : `fuso ${fuso}`);

// ---------- Desenho da seção ----------
function grupo(titulo, nota) {
  const el = criar('div', 'regras__grupo');
  el.append(criar('h3', 'regras__titulo', titulo));
  if (nota) el.append(criar('p', 'regras__nota', nota));
  return el;
}

function desenhar(corpo, r) {
  const pontos = grupo('Pontos por item', 'Cada item descartado vale os pontos do seu tipo de resíduo.');
  const listaPontos = criar('dl', 'regras__lista');
  for (const t of r.tipos) {
    const linha = criar('div');
    linha.append(criar('dt', null, t.nome), criar('dd', null, pontosPorExtenso(t.pontos)));
    listaPontos.append(linha);
  }
  pontos.append(listaPontos);

  const niveis = grupo('Níveis', 'O nível sobe conforme o total de pontos.');
  const listaNiveis = criar('ol', 'regras__lista regras__lista--simples');
  r.niveis.forEach((n, i) => {
    const proximo = r.niveis[i + 1];
    const faixa = proximo ? `de ${formatoNumero.format(n.de)} a ${pontosPorExtenso(proximo.de - 1)}` : `${pontosPorExtenso(n.de)} ou mais`;
    const item = criar('li');
    item.append(criar('span', 'regras__nome', n.nome), criar('span', 'regras__valor', faixa));
    listaNiveis.append(item);
  });
  niveis.append(listaNiveis);

  const medalhas = grupo('Medalhas', 'Medalhas reconhecem sua constância. Elas não dão pontos.');
  const listaMedalhas = criar('ul', 'regras__lista regras__lista--simples');
  for (const m of r.medalhas) {
    const item = criar('li');
    item.append(criar('span', 'regras__nome', m.nome), criar('span', 'regras__valor', m.descricao));
    listaMedalhas.append(item);
  }
  medalhas.append(listaMedalhas);

  const limites = grupo('Regras e limites do descarte');
  const listaLimites = criar('ul', 'regras__lista regras__lista--simples');
  for (const texto of [
    `Você precisa estar a até ${formatoNumero.format(r.raioM)} m do ponto de coleta. O site confere pela localização do seu navegador, e ela não é guardada.`,
    `Cada registro aceita de 1 a ${itensPorExtenso(r.quantidadeMax)}.`,
    `No máximo ${formatoNumero.format(r.maxRegistros)} registros por dia.`,
    `No máximo ${itensPorExtenso(r.maxItens)} por dia.`,
    `O dia vai de meia-noite a meia-noite, no ${nomeDoFuso(r.fuso)}.`,
    'O peso em quilos é uma estimativa: peso médio por item, por tipo de resíduo. Não é uma medição.',
  ]) {
    listaLimites.append(criar('li', null, texto));
  }
  limites.append(listaLimites);

  corpo.replaceChildren(pontos, niveis, medalhas, limites);
}

/** Liga a seção. No modo demonstração (sem banco) ela some, junto com o link do menu. */
export function iniciarRegras() {
  const secao = $('#pontos');
  const corpo = $('#regras-corpo');
  if (!secao || !corpo) return;
  if (modoDemonstracao()) {
    secao.hidden = true;
    const itemMenu = $('[data-pontos-nav]');
    if (itemMenu) itemMenu.hidden = true;
    return;
  }

  async function carregar() {
    corpo.setAttribute('aria-busy', 'true');
    corpo.replaceChildren(criar('p', 'lista__estado', 'Carregando as regras…'));
    try {
      desenhar(corpo, await obterRegras());
    } catch (erro) {
      const tentar = criar('button', 'botao botao--suave', 'Tentar de novo');
      tentar.type = 'button';
      tentar.addEventListener('click', carregar);
      const aviso = criar('p', 'lista__estado', erro.message || 'Não foi possível carregar as regras agora.');
      aviso.setAttribute('role', 'alert');
      corpo.replaceChildren(aviso, tentar);
    } finally {
      corpo.setAttribute('aria-busy', 'false');
    }
  }
  carregar();
}
