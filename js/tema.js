// =====================================================================
// Ecotroca — tema de cores (Automático, Claro, Escuro)
// A escolha vive no atributo data-theme do <html> ("light" ou "dark"; sem atributo = Automático,
// que segue o aparelho pelo CSS) e no localStorage. Sem localStorage o site funciona do mesmo jeito,
// só não lembra a escolha. O atributo também é aplicado por um script curto no <head> de cada página,
// antes de desenhar, para a página não piscar.
// Páginas sem o botão (Privacidade, Termos, 404) só respeitam a escolha salva.
// =====================================================================

const CHAVE = 'ecotroca-tema';
const NOMES = { auto: 'Automático', light: 'Claro', dark: 'Escuro' };
const CORES_PADRAO = { light: '#FAF8F3', dark: '#14120F' }; // só se não der para ler --papel

const html = document.documentElement;
const escuroDoAparelho = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function lerEscolha() {
  try {
    const guardado = localStorage.getItem(CHAVE);
    return guardado === 'light' || guardado === 'dark' ? guardado : 'auto';
  } catch (erro) {
    return 'auto';
  }
}

function guardar(escolha) {
  try {
    if (escolha === 'auto') localStorage.removeItem(CHAVE);
    else localStorage.setItem(CHAVE, escolha);
  } catch (erro) {
    /* sem armazenamento: vale só nesta visita */
  }
}

const escolhaAtual = () => (html.dataset.theme === 'light' || html.dataset.theme === 'dark' ? html.dataset.theme : 'auto');
const temaEfetivo = () => (escolhaAtual() === 'auto' ? (escuroDoAparelho && escuroDoAparelho.matches ? 'dark' : 'light') : escolhaAtual());

/** O meta theme-color (barra do navegador no celular) acompanha a cor de fundo do tema em uso. */
function atualizarMeta() {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) return;
  const lida = getComputedStyle(html).getPropertyValue('--papel').trim();
  meta.setAttribute('content', lida || CORES_PADRAO[temaEfetivo()]);
}

function marcarBotoes() {
  const atual = escolhaAtual();
  for (const botao of document.querySelectorAll('[data-tema]')) {
    botao.setAttribute('aria-pressed', String(botao.dataset.tema === atual));
  }
}

function aplicar(escolha) {
  if (escolha === 'auto') html.removeAttribute('data-theme');
  else html.setAttribute('data-theme', escolha);
  atualizarMeta();
  marcarBotoes();
}

aplicar(lerEscolha());
if (escuroDoAparelho) {
  // No automático, trocar o tema do aparelho com a página aberta atualiza a barra do navegador
  escuroDoAparelho.addEventListener('change', atualizarMeta);
}

for (const botao of document.querySelectorAll('[data-tema]')) {
  botao.addEventListener('click', () => {
    const escolha = botao.dataset.tema;
    guardar(escolha);
    aplicar(escolha);
    const anuncio = document.querySelector('#anuncio');
    if (anuncio) anuncio.textContent = `Tema: ${NOMES[escolha]}.`;
  });
}
