════════════════════════════════════════════════════════════
  SËTU — Agent Transport WhatsApp pour Dakar
  Version 1.0 MVP
════════════════════════════════════════════════════════════

─────────────────────────────────────────────
  QU'EST-CE QUE SËTU ?
─────────────────────────────────────────────

Sëtu est un agent intelligent sur WhatsApp qui aide les
usagers des bus Dem Dikk à Dakar à savoir où sont les bus
en temps réel, grâce aux signalements de la communauté.

Quelqu'un voit le bus 15 à Liberté 5 ?
Il envoie "Bus 15 à Liberté 5" à Sëtu.
Sëtu enregistre et prévient automatiquement toutes les
personnes qui attendent ce bus.

Sëtu parle : Français, Wolof, Pulaar, Anglais.


─────────────────────────────────────────────
  STRUCTURE DU PROJET
─────────────────────────────────────────────

setu/
├── main.py                  → Point d'entrée, webhook WhatsApp
├── agents/
│   ├── router.py            → Classifie l'intention du message
│   ├── extractor.py         → Extrait ligne + position des messages
│   └── responder.py         → Génère les réponses (Groq + Gemini)
├── db/
│   ├── supabase.py          → Connexion à la base de données
│   └── context.py           → Toutes les fonctions base de données
├── rag/
│   └── retriever.py         → Recherche dans les données transport
├── services/
│   ├── whatsapp.py          → Envoi/réception messages WhatsApp
│   ├── whisper.py           → Transcription audio → texte
│   └── language.py          → Détection de langue
├── .env.example             → Variables d'environnement à remplir
├── requirements.txt         → Dépendances Python
└── Procfile                 → Démarrage serveur (Railway/Render)


─────────────────────────────────────────────
  LOGIQUE COMPLÈTE DU PIPELINE
─────────────────────────────────────────────

Quand un utilisateur envoie un message à Sëtu :

  1. RÉCEPTION
     └─ WhatsApp envoie le message au webhook /webhook
     └─ Si audio → transcription via Groq Whisper

  2. CONTEXTE
     └─ Récupère ou crée le contact dans Supabase
     └─ Récupère ou crée la conversation
     └─ Récupère les 10 derniers messages (mémoire)

  3. ANALYSE
     └─ Détecte la langue (Wolof, Français, Pulaar, Anglais)
     └─ Classifie l'intention du message :
        - signalement  → "Bus 15 à Liberté 5"
        - question     → "Le bus 15 est où ?"
        - abonnement   → "Préviens-moi pour le Bus 15"
        - complaint    → Réclamation
        - escalate     → Demande un humain
        - out_of_scope → Hors sujet

  4. TRAITEMENT SELON L'INTENTION

     CAS SIGNALEMENT :
     ├─ Extrait : ligne (ex: "15") + position (ex: "Liberté 5")
     ├─ Enregistre dans la table "signalements" Supabase
     ├─ Cherche tous les abonnés de cette ligne
     ├─ Envoie une alerte WhatsApp à chaque abonné
     └─ Remercie le signaleur avec le nombre de personnes aidées

     CAS ABONNEMENT :
     ├─ Extrait : ligne + arrêt + heure souhaitée
     ├─ Enregistre dans la table "abonnements" Supabase
     └─ Confirme à l'utilisateur qu'il sera alerté

     CAS QUESTION :
     ├─ Cherche les signalements récents de la ligne mentionnée
     ├─ Si aucun signalement → cherche dans la knowledge_base
     └─ Génère une réponse avec l'IA (Groq ou Gemini)

     CAS ESCALADE :
     ├─ Marque la conversation comme "escalated" dans Supabase
     ├─ Crée un ticket dans la table "tickets"
     └─ Envoie un message de transfert vers un humain

  5. RÉPONSE
     └─ Wolof → Google Gemini 2.0 Flash
     └─ Autres langues → Groq Llama 3.3 70B
     └─ Sauvegarde la réponse dans Supabase


─────────────────────────────────────────────
  BASE DE DONNÉES SUPABASE — TABLES NÉCESSAIRES
─────────────────────────────────────────────

Utilise le fichier setu_supabase.sql pour créer les tables.
(Supabase → SQL Editor → coller → Execute)

Tables créées :
  contacts       → Profils des utilisateurs WhatsApp
  conversations  → Historique des conversations
  messages       → Tous les messages échangés
  signalements   → Positions de bus signalées par les usagers
  abonnements    → Abonnements des usagers aux lignes
  lignes         → Les 22 lignes Dem Dikk
  arrets         → Les 592 arrêts (aller + retour)
  tickets        → Escalades vers agents humains
  knowledge_base → Informations générales (optionnel)


─────────────────────────────────────────────
  VARIABLES D'ENVIRONNEMENT (.env)
─────────────────────────────────────────────

Copie .env.example en .env et remplis :

  BUSINESS_NAME        → "Sëtu"
  WHATSAPP_TOKEN       → Token Meta (WhatsApp Business API)
  WHATSAPP_PHONE_ID    → ID du numéro WhatsApp Business
  VERIFY_TOKEN         → Token de vérification webhook (dakar2025)
  TENANT_ID            → Ton ID tenant dans Supabase
  GROQ_API_KEY         → Clé API Groq (groq.com)
  GEMINI_API_KEY       → Clé API Google Gemini
  SUPABASE_URL         → URL de ton projet Supabase
  SUPABASE_SERVICE_KEY → Clé service Supabase


─────────────────────────────────────────────
  DÉPLOIEMENT RAILWAY
─────────────────────────────────────────────

  1. Push le code sur GitHub
  2. Railway → New Project → Deploy from GitHub
  3. Ajouter toutes les variables d'environnement dans Railway
  4. Railway déploie automatiquement

  URL du webhook à mettre sur Meta Developer :
  https://ton-projet.railway.app/webhook


─────────────────────────────────────────────
  STACK TECHNIQUE
─────────────────────────────────────────────

  FastAPI          → Serveur web Python (webhook)
  Groq + Llama 3.3 → LLM principal (FR, EN, Pulaar)
  Gemini 2.0 Flash → LLM pour le Wolof
  Groq Whisper     → Transcription des messages vocaux
  Supabase         → Base de données PostgreSQL
  WhatsApp API     → Canal de communication (Meta)
  Railway          → Hébergement du serveur


─────────────────────────────────────────────
  EXEMPLES D'UTILISATION
─────────────────────────────────────────────

  Signalement :
  User → "Bus 15 à Liberté 5"
  Sëtu → "✅ Merci ! Bus 15 à Liberté 5 enregistré.
           Tu viens d'aider 3 personne(s) 🙏"

  Question :
  User → "Le bus 15 est où ?"
  Sëtu → "🚌 Dernier signalement Bus 15 :
           Liberté 5 — il y a 4 minutes.
           Il devrait arriver bientôt !"

  Abonnement :
  User → "Préviens-moi pour le Bus 15 depuis Liberté 5"
  Sëtu → "🔔 C'est noté ! Je t'alerterai dès que
           le Bus 15 est signalé près de Liberté 5."

  Alerte automatique (reçue par l'abonné) :
  Sëtu → "🔔 Bus 15 signalé à Liberté 5 il y a
           quelques instants. Communauté Sëtu 🚌"


════════════════════════════════════════════════════════════
  Projet développé à Dakar — 2026
════════════════════════════════════════════════════════════
