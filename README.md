# 🚌 Xëtu — Agent IA Transport en Commun · Dakar

> Assistant conversationnel pour les bus **Dem Dikk** à Dakar, Sénégal.  
> Disponible sur **WhatsApp · Telegram · Web (PWA)**

[![Version](https://img.shields.io/badge/version-8.2-blue)](.)
[![Python](https://img.shields.io/badge/python-3.11+-green)](.)
[![Framework](https://img.shields.io/badge/framework-FastAPI-009688)](.)
[![LLM](https://img.shields.io/badge/LLM-Groq%20llama--3.3--70b-orange)](.)
[![Deploy](https://img.shields.io/badge/deploy-Railway-blueviolet)](.)
[![DB](https://img.shields.io/badge/db-Supabase%20PostgreSQL-3ecf8e)](.)

---

## Pourquoi Xëtu ?

À Dakar, les bus Dem Dikk n'ont **pas de GPS embarqué**. Les usagers ne savent pas si leur bus approche, s'il est en retard, ni quel itinéraire prendre entre deux quartiers.

**Xëtu** résout ce problème par le **crowdsourcing** : les usagers signalent eux-mêmes les bus qu'ils voient, et l'agent agrège ces données en temps réel pour renseigner toute la communauté.

---

## Fonctionnalités

| Feature | Description |
|---|---|
| 📍 **Localisation crowdsourcée** | Signalements communautaires avec anti-fraude intégré |
| 🗺️ **Itinéraires multi-lignes** | Calcul de trajet entre quartiers (marche + correspondances) |
| 🔔 **Alertes push** | Abonnement aux notifications pour une ligne / un arrêt |
| 🗣️ **Bilingue natif** | Français et Wolof, détection automatique |
| 📊 **Dashboard temps réel** | Carte PWA avec positions interpolées des bus actifs |
| 🎙️ **Messages vocaux** | Transcription audio via Whisper |

---

## Stack technique

```
Backend          FastAPI (Python 3.11+)         déployé sur Railway
Agent            LangGraph ReAct — 6 tools
LLM principal    Groq llama-3.3-70b-versatile   temperature=0, max_tokens=1024
LLM fallback     Gemini 2.0 Flash               rate limit 429 Groq → fallback auto
Base de données  PostgreSQL via Supabase
Historique       LangGraph PostgreSQL Checkpointer
Canaux           WhatsApp Business API · Telegram Bot · WebSocket
Données réseau   routes_geometry_v13.json — 77 lignes, 3129 arrêts, travel_time OSRM
RAG              Retriever pour questions réseau complexes
Push             Web Push PWA (table push_subscriptions)
Voix             OpenAI Whisper (transcription audio WhatsApp)
```

---

## Architecture fichiers

```
xetu/
├── main.py                    # Orchestrateur FastAPI — ZÉRO logique métier
├── agent/
│   ├── xetu_agent.py          # Agent ReAct LangGraph, fallback Groq→Gemini, checkpointer
│   ├── tools.py               # 6 tools LangGraph
│   ├── soul.py                # System prompt (personnalité Xëtu)
│   ├── graph.py               # DemDikkGraph : routage walk-aware, fuzzy matching, Haversine
│   ├── extractor.py           # Extraction entités (ligne, arrêt) depuis messages bruts
│   ├── router.py              # extract_qualites() — enrichissement intent
│   ├── normalizer.py          # Normalisation texte + normalize_for_cache
│   ├── intent_cache.py        # Cache intent — court-circuit patterns fréquents
│   └── checkpointer.py        # get_checkpointer() async — PostgreSQL checkpointer
├── api/
│   ├── buses.py               # GET /api/buses — positions estimées (interpolation temporelle)
│   ├── leaderboard.py         # GET /api/leaderboard
│   ├── report.py              # GET /api/report
│   └── push.py                # Endpoints Web Push
├── config/
│   └── settings.py            # Variables d'env, VALID_LINES dynamique, constantes métier
├── core/
│   ├── network.py             # NETWORK dict, get_stops(), get_graph_data() — adaptateur v13
│   ├── anti_fraud.py          # is_blacklisted, is_spam_pattern, check_distance_coherence, compute_confidence
│   ├── security.py            # verify_webhook_signature, validate_phone, check_rate_limit
│   ├── session_manager.py     # get_context, is_abandon, reset_context, set_session
│   └── queue_manager.py       # asynccontextmanager process() — sérialisation par user
├── db/
│   ├── client.py              # get_client() → Supabase client singleton
│   └── queries.py             # ⚠️ SEUL fichier qui touche Supabase
├── skills/
│   ├── signalement.py         # handle() + notify_abonnes()
│   ├── itineraire.py          # handle_origin_response()
│   └── question.py            # handle_arret_response()
├── rag/
│   └── retriever.py           # retrieve(query, ligne) — questions réseau complexes
├── memory/
│   └── user_memory.py         # update_after_message() — mémoire utilisateur persistante
├── services/
│   ├── whatsapp.py            # send_message(), parse_incoming_message()
│   ├── telegram.py            # send_message(), parse_incoming_update()
│   ├── whisper.py             # transcribe(audio_id) — transcription vocale
│   ├── language.py            # detect_language()
│   └── websocket.py           # handle_websocket()
├── heartbeat/
│   └── runner.py              # start_heartbeat() — tâches périodiques
├── Dashboard/
│   └── js/
│       ├── home.js            # Carte accueil, markers bus, animation, GTFS L1+L4
│       ├── reader.js          # Bandeau arrêt courant, scroll automatique
│       ├── app.js             # Orchestrateur dashboard, DEMO_MODE
│       ├── ws.js              # Client WebSocket, reconnexion, ping
│       ├── store.js           # État global dashboard
│       ├── map.js             # Ancien fichier carte (non actif sur accueil)
│       └── constants.js       # API_BASE, SESSION_PREFIX
├── sw.js                      # Service Worker PWA
└── routes_geometry_v13.json   # Source de vérité réseau (77 lignes, 3129 arrêts)
```

---

## Les 6 tools LangGraph

| Tool | Description |
|---|---|
| `calculate_route(origin, destination)` | Itinéraire bus. Walk-aware (rayon 900m). Travel times OSRM. |
| `get_recent_sightings(ligne)` | Signalements actifs pour une ligne. TTL 20 min. Max 3 résultats. |
| `report_bus(ligne, arret, message_original)` | Enregistre un signalement avec pipeline anti-fraude complet. |
| `manage_subscription(action, ligne, arret?, heure?)` | Subscribe/unsubscribe alertes bus. |
| `get_bus_info(query, ligne?)` | Info réseau : arrêts, horaires, fréquences + RAG. |
| `extract_entities(text)` | Extraction ligne/arrêt depuis message ambigu. |

---

## Pipeline message (main.py)

```
1.  Validation longueur (1–500 chars)
2.  normalize(text)
3.  get_context(phone) — session active ?
4.  get_or_create_contact + get_or_create_conversation
5.  Welcome message si 1ère visite
6.  detect_language(text)
7.  save_message(user)
8.  PRIORITÉ 1 : is_abandon → reset session
9.  PRIORITÉ 2 : session active → _handle_session_active
10. PRIORITÉ 3 : xetu_run(message, phone, langue) → Agent LangGraph
11. save_message(assistant)
12. user_memory.update_after_message()
```

---

## Schéma base de données (Supabase)

| Table | Colonnes clés |
|---|---|
| `contacts` | phone, langue, fiabilite_score (0–1), profil_json |
| `conversations` | contact_id, statut (active / escalated) |
| `messages` | conversation_id, role, content, langue, intent |
| `signalements` | ligne, position, phone, timestamp, expires_at, valide, qualite |
| `abonnements` | phone, ligne, arret, heure_alerte, actif |
| `sessions` | phone, etat, ligne, signalement (json), destination, expires_at |
| `push_subscriptions` | phone, endpoint, p256dh, auth |
| `network_memory` | ligne, intervalle_moyen |
| `schedules` | ligne, arret, heure_passage |
| `tickets` | phone, motif, priorite, statut |
| `lignes` | numero, actif |

> ⚠️ **Règle absolue** : `db/queries.py` est le **seul fichier** autorisé à effectuer des requêtes Supabase.

---

## Constantes métier clés

```python
SIGNALEMENT_TTL_MINUTES        = 20
DEDUP_WINDOW_SECONDS           = 120
SESSION_CONTEXT_TTL_SECONDS    = 1800   # 30 min
RATE_LIMIT_PER_PHONE_PER_MIN   = 10
_WALK_SPEED_MS                 = 1.3    # m/s
_SECS_PER_STOP                 = 120    # fallback si pas de travel_time OSRM
_TRANSFER_PENALTY              = 360    # secondes
_RADIUS_MAX_M                  = 900    # rayon max marche
```

---

## Anti-fraude signalements

Chaque signalement passe par un pipeline de validation avant insertion :

1. **Blacklist** — numéro banni → rejeté silencieusement
2. **Spam pattern** — message suspect (répétition, bot) → rejeté
3. **Distance cohérence** — arrêt déclaré cohérent avec localisation estimée de l'usager
4. **Score de confiance** — calculé depuis `fiabilite_score` du contact + corroboration

---

## Langues et routing LLM

| Langue | LLM utilisé |
|---|---|
| Français | Groq llama-3.3-70b-versatile |
| Wolof | Gemini 2.0 Flash |
| Fallback (rate limit 429 Groq) | Gemini 2.0 Flash automatique |

La détection de langue est automatique à chaque message via `services/language.py`.

---

## Dashboard PWA

Le dashboard `xetudashbord.pages.dev` est une PWA Leaflet qui affiche :

- Les bus actifs (position interpolée via `api/buses.py`)
- Le tracé de la ligne sélectionnée
- Un bandeau "reader" qui défile sur les arrêts en temps réel
- Mode démo : Ligne 1 + Ligne 4 avec données GTFS réelles

### Architecture JS Dashboard

| Fichier | Rôle |
|---|---|
| `home.js` | Carte accueil, markers bus, sélection, animation |
| `reader.js` | Bandeau arrêt courant, scroll automatique |
| `app.js` | Orchestrateur, `DEMO_MODE=true` bloque l'API Railway |
| `ws.js` | Client WebSocket, reconnexion exponentielle, ping 25s |
| `sw.js` | Service Worker PWA — incrémenter `CACHE_VERSION` à chaque sprint |

### Bugs actifs (session 22 mars 2026)

| ID | Sévérité | Symptôme | Statut |
|---|---|---|---|
| BUG-1 | CRITIQUE | `reader.js` défile trop vite (offsetWidth=0) | En cours |
| BUG-2 | CRITIQUE | `minutes_ago` figé — SW cache l'ancienne version | En cours |
| BUG-3 | MOYEN | Carte trop dézoomée au démarrage | Partiellement corrigé |
| BUG-4 | MOYEN | Marker bus 4 affiche un carré (Leaflet divIcon) | Non appliqué |
| BUG-5 | MOYEN | Tracés L1+L4 visibles sans sélection | Non investigué |
| BUG-6 | MINEUR | SW cache les anciens fichiers JS | Workaround manuel |

---

## Variables d'environnement

```env
# LLM
GROQ_API_KEY=
GEMINI_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# WhatsApp Business API
WHATSAPP_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
VERIFY_TOKEN=

# Telegram
TELEGRAM_BOT_TOKEN=

# Railway
PORT=8000
```

---

## Installation locale

```bash
# 1. Cloner le repo
git clone https://github.com/<org>/xetu.git && cd xetu

# 2. Environnement virtuel
python -m venv .venv && source .venv/bin/activate

# 3. Dépendances
pip install -r requirements.txt

# 4. Variables d'environnement
cp .env.example .env  # puis remplir les clés

# 5. Lancer
uvicorn main:app --reload --port 8000
```

---

## Principes de design

1. **Fiabilité > Features** — Chaque feature doit fonctionner sur WhatsApp avec réseau 3G lent
2. **Communautaire** — Les données viennent des usagers, pas d'un GPS
3. **Bilingue natif** — Wolof et Français, pas de traduction mécanique
4. **Anti-fraude intégré** — Score de confiance sur chaque signalement
5. **Graceful degradation** — Groq down → Gemini. DB down → mode dégradé. Jamais de crash silencieux.
6. **Zéro logique métier dans main.py** — `main.py` orchestre, `tools/` et `skills/` exécutent
7. **`queries.py` = seul fichier qui touche Supabase**

---

## Versioning

| Version | Highlights |
|---|---|
| V1.0 | MVP WhatsApp — signalements + itinéraires basiques |
| V3.0 | Agent LangGraph ReAct, 4 tools |
| V5.0 | Wolof natif, routing LLM par langue |
| V6.0 | Anti-fraude complet, score de confiance |
| V7.0 | RAG réseau, push notifications PWA |
| V8.0 | Checkpointer PostgreSQL, SOUL V8, Gemini fallback |
| **V8.2** | Dashboard PWA Leaflet, reader temps réel, démo L1+L4 |
| V8.3 | Support messages location Telegram (GPS) — en cours |

---

## Licence

Projet privé — © 2025-2026 Équipe Xëtu. Tous droits réservés.
