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
        # Met à jour la langue si elle a changé
        if contact.get("langue") != langue:
            db.table("contacts").update({"langue": langue}).eq("phone", phone).execute()
            contact["langue"] = langue
        return contact
    # Crée le contact
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

def save_signalement(ligne: str, arret: str, phone: str) -> dict:
    db = get_client()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SIGNALEMENT_TTL_MINUTES)
    res = db.table("signalements").insert({
        "ligne_id": ligne,
        "arret_nom": arret,
        "phone": phone,
        "expires_at": expires_at.isoformat()
    }).execute()
    return res.data[0]


def get_signalements_actifs(ligne: str) -> list[dict]:
    """Retourne les signalements non expirés pour une ligne."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("signalements")
             .select("*")
             .eq("ligne_id", ligne)
             .gt("expires_at", now)
             .order("created_at", desc=True)
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
    # Lignes actives
    lignes_res = db.table("lignes").select("numero").eq("actif", True).execute()
    toutes = {l["numero"] for l in (lignes_res.data or [])}
    # Lignes avec signalement récent
    sig_res = (db.table("signalements")
                 .select("ligne_id")
                 .gt("created_at", since)
                 .execute())
    actives = {s["ligne_id"] for s in (sig_res.data or [])}
    return list(toutes - actives)


# ── Abonnements ───────────────────────────────────────────

def get_abonnes(ligne: str) -> list[dict]:
    db = get_client()
    res = (db.table("abonnements")
             .select("phone, arret_nom, heure_souhaitee")
             .eq("ligne_id", ligne)
             .eq("actif", True)
             .execute())
    return res.data or []


def create_abonnement(phone: str, ligne: str, arret: str,
                      heure_souhaitee: str | None = None) -> dict:
    db = get_client()
    # Vérifie si existe déjà
    existing = (db.table("abonnements")
                  .select("id")
                  .eq("phone", phone)
                  .eq("ligne_id", ligne)
                  .eq("actif", True)
                  .execute())
    if existing.data:
        return existing.data[0]
    res = db.table("abonnements").insert({
        "phone": phone,
        "ligne_id": ligne,
        "arret_nom": arret or "",
        "heure_souhaitee": heure_souhaitee,
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
             .eq("heure_souhaitee", heure_cible)
             .execute())
    return res.data or []


# ── Tickets (escalade) ────────────────────────────────────

def create_ticket(phone: str, motif: str) -> dict:
    db = get_client()
    res = db.table("tickets").insert({
        "phone": phone,
        "motif": motif,
        "priorite": "normale",
        "statut": "ouvert"
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


# ── Sessions (état multi-tour persisté dans Supabase) ─────

SESSION_CONTEXT_TTL_SECONDS = 600  # FIX #4 : 10 min (was 2 min)


def get_session(phone: str) -> dict | None:
    """Retourne la session active non expirée. None si absente/expirée."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("sessions")
             .select("*")
             .eq("phone", phone)
             .gt("expires_at", now)
             .limit(1)
             .execute())
    return res.data[0] if res.data else None


def set_session(phone: str, etat: str,
                ligne: str | None = None,
                signalement: dict | None = None,
                destination: str | None = None) -> dict:
    """Crée ou remplace la session (UPSERT). TTL = 10 min."""
    db = get_client()
    expires_at = (datetime.now(timezone.utc)
                  + timedelta(seconds=SESSION_CONTEXT_TTL_SECONDS)).isoformat()
    data = {
        "phone":       phone,
        "etat":        etat,
        "ligne":       ligne,
        "signalement": signalement,
        "destination": destination,
        "expires_at":  expires_at,
    }
    res = (db.table("sessions")
             .upsert(data, on_conflict="phone")
             .execute())
    return res.data[0]


def delete_session(phone: str):
    db = get_client()
    db.table("sessions").delete().eq("phone", phone).execute()


def purge_sessions_expires():
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    db.table("sessions").delete().lt("expires_at", now).execute()
