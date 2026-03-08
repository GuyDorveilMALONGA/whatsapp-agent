"""
db/queries.py
Règle absolue : SEUL fichier qui touche Supabase.
Tous les autres modules passent par ici.
"""
from datetime import datetime, timedelta, timezone
from db.client import get_client
from config.settings import SIGNALEMENT_TTL_MINUTES


# ── Contacts ──────────────────────────────────────────────

def get_or_create_contact(phone: str, langue: str = "fr") -> dict:
    db = get_client()
    res = db.table("contacts").select("*").eq("phone", phone).execute()
    if res.data:
        contact = res.data[0]
        if contact.get("langue") != langue:
            db.table("contacts").update({"langue": langue}).eq("phone", phone).execute()
            contact["langue"] = langue
        return contact
    new = db.table("contacts").insert({
        "phone": phone,
        "langue": langue,
        "fiabilite_score": 0.5,
        "profil_json": {}
    }).execute()
    return new.data[0]


# ── Conversations ─────────────────────────────────────────

def get_or_create_conversation(contact_id: str) -> dict:
    db = get_client()
    res = (db.table("conversations")
             .select("*")
             .eq("contact_id", contact_id)
             .eq("statut", "active")
             .order("created_at", desc=True)
             .limit(1)
             .execute())
    if res.data:
        return res.data[0]
    new = db.table("conversations").insert({
        "contact_id": contact_id,
        "statut": "active"
    }).execute()
    return new.data[0]


def mark_conversation_escalated(conversation_id: str):
    db = get_client()
    db.table("conversations").update({"statut": "escalated"}).eq("id", conversation_id).execute()


# ── Messages ──────────────────────────────────────────────

def save_message(conversation_id: str, role: str, content: str,
                 langue: str = "fr", intent: str | None = None):
    db = get_client()
    db.table("messages").insert({
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "langue": langue,
        "intent": intent
    }).execute()


def get_recent_messages(conversation_id: str, limit: int = 10) -> list[dict]:
    db = get_client()
    res = (db.table("messages")
             .select("role, content")
             .eq("conversation_id", conversation_id)
             .order("created_at", desc=True)
             .limit(limit)
             .execute())
    return list(reversed(res.data or []))


# ── Signalements ──────────────────────────────────────────
# Colonnes utilisées : ligne (NOT NULL), position (NOT NULL),
#                      expires_at, phone, lat, lng, valide

def save_signalement(ligne: str, arret: str, phone: str) -> dict:
    db = get_client()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SIGNALEMENT_TTL_MINUTES)
    res = db.table("signalements").insert({
        "ligne": ligne,
        "position": arret,      # colonne NOT NULL dans Supabase
        "phone": phone,
        "expires_at": expires_at.isoformat(),
        "valide": True
    }).execute()
    return res.data[0]


def get_signalements_actifs(ligne: str) -> list[dict]:
    """Retourne les signalements non expirés pour une ligne."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("signalements")
             .select("*")
             .eq("ligne", ligne)
             .gt("expires_at", now)
             .eq("valide", True)
             .order("timestamp", desc=True)
             .execute())
    return res.data or []


def purge_signalements_expires():
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    db.table("signalements").delete().lt("expires_at", now).execute()


def get_lignes_silencieuses(seuil_minutes: int) -> list[str]:
    """Retourne les numéros de lignes sans signalement récent."""
    db = get_client()
    since = (datetime.now(timezone.utc) - timedelta(minutes=seuil_minutes)).isoformat()
    lignes_res = db.table("lignes").select("numero").eq("actif", True).execute()
    toutes = {l["numero"] for l in (lignes_res.data or [])}
    sig_res = (db.table("signalements")
                 .select("ligne")
                 .gt("timestamp", since)
                 .eq("valide", True)
                 .execute())
    actives = {s["ligne"] for s in (sig_res.data or [])}
    return list(toutes - actives)


# ── Abonnements ───────────────────────────────────────────
# Colonnes utilisées : ligne (NOT NULL), arret, heure_alerte,
#                      actif, phone

def get_abonnes(ligne: str) -> list[dict]:
    db = get_client()
    res = (db.table("abonnements")
             .select("phone, arret, heure_alerte")
             .eq("ligne", ligne)
             .eq("actif", True)
             .execute())
    return res.data or []


def create_abonnement(phone: str, ligne: str, arret: str,
                      heure_souhaitee: str | None = None) -> dict:
    db = get_client()
    existing = (db.table("abonnements")
                  .select("id")
                  .eq("phone", phone)
                  .eq("ligne", ligne)
                  .eq("actif", True)
                  .execute())
    if existing.data:
        return existing.data[0]
    res = db.table("abonnements").insert({
        "phone": phone,
        "ligne": ligne,
        "arret": arret or "",
        "heure_alerte": heure_souhaitee,
        "actif": True
    }).execute()
    return res.data[0]


def get_abonnements_proactifs(avant_minutes: int = 15) -> list[dict]:
    """Abonnés dont l'heure habituelle approche dans X minutes."""
    db = get_client()
    now = datetime.now(timezone.utc)
    heure_cible = (now + timedelta(minutes=avant_minutes)).strftime("%H:%M")
    res = (db.table("abonnements")
             .select("*")
             .eq("actif", True)
             .eq("heure_alerte", heure_cible)
             .execute())
    return res.data or []


# ── Tickets (escalade) ────────────────────────────────────
# Colonnes utilisées : motif, priorite, status

def create_ticket(phone: str, motif: str) -> dict:
    db = get_client()
    # Récupère la conversation active pour lier le ticket
    contact_res = db.table("contacts").select("id").eq("phone", phone).execute()
    contact_id = contact_res.data[0]["id"] if contact_res.data else None
    conversation_id = None
    if contact_id:
        conv_res = (db.table("conversations")
                      .select("id")
                      .eq("contact_id", contact_id)
                      .eq("statut", "active")
                      .order("created_at", desc=True)
                      .limit(1)
                      .execute())
        if conv_res.data:
            conversation_id = conv_res.data[0]["id"]
    res = db.table("tickets").insert({
        "motif": motif,
        "priorite": "normale",
        "status": "open",
        "conversation_id": conversation_id
    }).execute()
    return res.data[0]


# ── Lignes (données réseau) ───────────────────────────────

def get_all_lignes() -> list[dict]:
    db = get_client()
    res = db.table("lignes").select("*").eq("actif", True).execute()
    return res.data or []


def ligne_existe(numero: str) -> bool:
    db = get_client()
    res = db.table("lignes").select("id").eq("numero", numero).execute()
    return bool(res.data)