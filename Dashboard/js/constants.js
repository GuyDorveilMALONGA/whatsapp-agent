/**
 * js/constants.js — V1.0 App Passager
 * Adapté depuis constants.js V4.0 du dashboard.
 * Retiré : tout ce qui est spécifique au dashboard desktop.
 */

export const API_BASE      = 'https://web-production-ccab8.up.railway.app';
export const WA_NUMBER     = '221XXXXXXXXX'; // ← remplacer par le vrai numéro
export const REFRESH_SEC   = 30;
export const SESSION_PREFIX = 'web_';

export const LIGNE_NAMES = {
  '1':       'Parcelles Assainies ↔ Place Leclerc',
  '2':       'Daroukhane ↔ Place Leclerc',
  '4':       'Liberté 5 ↔ Place Leclerc',
  '5':       'Guédiawaye ↔ Palais 1',
  '6':       'Guédiawaye ↔ Palais 1',
  '7':       'Ouakam ↔ Palais 2',
  '8':       'Aéroport LSS ↔ Palais 2',
  '9':       'Liberté 6 ↔ Palais 2',
  '10':      'Liberté 5 ↔ Palais 2',
  '11':      'Keur Massar ↔ Lat Dior',
  '12':      'Guédiawaye ↔ Palais 1',
  '13':      'Liberté 5 ↔ Palais 2',
  '15':      'Rufisque ↔ Palais 1',
  '16A':     'Malika ↔ Palais 1',
  '16B':     'Malika ↔ Palais 1',
  '18':      'Liberté 5 ↔ Centre-Ville',
  '20':      'Dieuppeul ↔ Centre-Ville',
  '23':      'Parcelles Assainies ↔ Palais 1',
  '121':     'Scat Urbam ↔ Leclerc',
  '213':     'Rufisque ↔ Dieuppeul',
  '217':     'Thiaroye ↔ Aéroport LSS',
  '218':     'Thiaroye ↔ Aéroport LSS',
  '219':     'Daroukhane ↔ Ouakam',
  '220':     'Rufisque ↔ Guédiawaye',
  '221':     'Gadaye ↔ Almadies',
  '227':     'Keur Massar ↔ Parcelles',
  '232':     'Baux Maraichers ↔ Aéroport LSS',
  '233':     'Baux Maraichers ↔ Palais 1',
  '234':     'Jaxaay ↔ Leclerc',
  '311':     'Lac Rose ↔ Keur Massar',
  '319':     'Liberté 6 ↔ Ouakam',
  '327':     'Keur Massar ↔ Parcelles',
  '501':     'Palais 2 ↔ Leclerc',
  '502':     'Gare Colobane (circulaire)',
  '503':     'Gare Colobane (circulaire)',
  'TAF TAF': 'Ouakam ↔ AIBD (Diamniadio)',
  'TO1':     'Ouakam ↔ Palais 2 (Taf Taf)',
  'RUF-YENNE': 'Rufisque ↔ Yenne',
};

export const LIGNES_CONNUES = new Set(Object.keys(LIGNE_NAMES));
