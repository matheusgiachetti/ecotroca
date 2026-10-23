// =====================================================================
// Ecotroca — dados dos pontos de coleta
// Busca no Supabase (tabela pontos_coleta). Se o Supabase não estiver
// configurado, usa data/pontos-exemplo.json (modo demonstração).
// =====================================================================

import { SUPABASE_URL, SUPABASE_ANON_KEY, naoConfigurado } from './config.js';

const SUPABASE_CDN = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.115.0/+esm';
const COLUNAS = 'id, nome, endereco, latitude, longitude, horario, residuos_aceitos, telefone, fonte, verificado';

export const modoDemonstracao = () => naoConfigurado(SUPABASE_URL) || naoConfigurado(SUPABASE_ANON_KEY);

let clienteSupabase = null;

/** Cria o cliente do Supabase sob demanda (só baixa a biblioteca se for usar). */
async function obterCliente() {
  if (!clienteSupabase) {
    const { createClient } = await import(SUPABASE_CDN);
    clienteSupabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
  }
  return clienteSupabase;
}

/** Garante tipos e valores previsíveis, descartando linhas sem coordenadas válidas. */
function normalizar(linha) {
  const lat = Number(linha.latitude);
  const lng = Number(linha.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  const texto = (v) => (typeof v === 'string' && v.trim() ? v.trim() : null);
  return {
    id: String(linha.id),
    nome: texto(linha.nome) || 'Ponto de coleta',
    endereco: texto(linha.endereco) || '',
    lat,
    lng,
    horario: texto(linha.horario),
    residuos: Array.isArray(linha.residuos_aceitos)
      ? linha.residuos_aceitos.map(texto).filter(Boolean)
      : [],
    telefone: texto(linha.telefone),
    fonte: texto(linha.fonte),
    verificado: linha.verificado === true,
  };
}

/**
 * Carrega os pontos de coleta.
 * @returns {Promise<{pontos: Array, demonstracao: boolean}>}
 */
export async function carregarPontos() {
  if (modoDemonstracao()) {
    const resposta = await fetch('data/pontos-exemplo.json', { cache: 'no-cache' });
    if (!resposta.ok) throw new Error(`Falha ao ler dados de exemplo (${resposta.status})`);
    const linhas = await resposta.json();
    return { pontos: linhas.map(normalizar).filter(Boolean), demonstracao: true };
  }

  const cliente = await obterCliente();
  const { data, error } = await cliente.from('pontos_coleta').select(COLUNAS).order('nome');
  if (error) throw new Error(error.message);
  return { pontos: (data || []).map(normalizar).filter(Boolean), demonstracao: false };
}
