"""
db/queries.py — V4.3
Règle absolue : SEUL fichier qui touche Supabase.

V4.3 :
  + get_derniers_signalements(ligne, limit) — même expirés
    Utilisé par core.frequencies pour estimer l'ETA
    (dernier signalement connu même si TTL dépassé)

V4.2 :
  + FIX : created_at → timestamp sur table signalements

V4.1 :
  + Horaires théoriques Moovit (save_schedules_batch, get_next_theoretical_bus)
  + Leaderboard limité à 30 jours

  ⚠️  get_leaderboard reste temporaire — migrer vers RPC Supabase
      (GROUP BY côté DB) avant 50k signalements
"""
from datetime import datetime, timedelta, timezone, date
import logging
from db.client import get_client
from config.settings import SIGNALEMENT_TTL_MINUTES

logger = logging.getLogger(__name__)


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
        "phone":           phone,
        "langue":          langue,
        "fiabilite_score": 0.5,
        "profil_json":     {}
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
        "statut":     "active"
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
        "role":            role,
        "content":         content,
        "langue":          langue,
        "intent":          intent
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
        "ligne":      ligne,
        "position":   arret,
        "phone":      phone,
        "expires_at": expires_at.isoformat()
    }).execute()
    return res.data[0]


def get_signalements_actifs(ligne: str) -> list[dict]:
    """Retourne les signalements non expirés pour une ligne donnée."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("signalements")
             .select("*")
             .eq("ligne", ligne)
             .gt("expires_at", now)
             .order("timestamp", desc=True)
             .execute())
    return res.data or []


def get_all_signalements_actifs() -> list[dict]:
    """Retourne tous les signalements non expirés (toutes lignes — pour /api/buses)."""
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("signalements")
             .select("*")
             .gt("expires_at", now)
             .order("timestamp", desc=True)
             .execute())
    return res.data or []


def get_derniers_signalements(ligne: str, limit: int = 1) -> list[dict]:
    """
    Retourne les derniers signalements d'une ligne — même expirés.
    Utilisé par core.frequencies pour estimer l'ETA quand aucun
    signalement actif n'est disponible.
    Ex : dernier signalement il y a 45 min sur ligne 8 (fréquence 45 min)
         → ETA estimé : ~0–10 min (bus probablement en route)
    """
    db = get_client()
    try:
        res = (db.table("signalements")
                 .select("ligne, position, timestamp, expires_at")
                 .eq("ligne", ligne)
                 .order("timestamp", desc=True)
                 .limit(limit)
                 .execute())
        return res.data or []
    except Exception as e:
        logger.error(f"[queries.get_derniers_signalements] ligne={ligne} erreur: {e}")
        return []


def purge_signalements_expires():
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    db.table("signalements").delete().lt("expires_at", now).execute()


def get_lignes_silencieuses(seuil_minutes: int) -> list[str]:
    """Retourne les numéros de lignes sans signalement récent."""
    db = get_client()
    since  = (datetime.now(timezone.utc) - timedelta(minutes=seuil_minutes)).isoformat()
    lignes = db.table("lignes").select("numero").eq("actif", True).execute()
    toutes = {l["numero"] for l in (lignes.data or [])}
    sigs   = (db.table("signalements")
                .select("ligne")
                .gt("timestamp", since)
                .execute())
    actives = {s["ligne"] for s in (sigs.data or [])}
    return list(toutes - actives)


# ── Abonnements ───────────────────────────────────────────

def get_abonnes(ligne: str) -> list[dict]:
    db = get_client()
    res = (db.table("abonnements")
             .select("phone, arret, heure_alerte")
             .eq("ligne", ligne)
             .eq("actif", True)
             .execute())
    return res.data or []


def create_abonnement(phone: str, ligne: str, arret: str,
                      heure_alerte: str | None = None) -> dict:
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
        "phone":        phone,
        "ligne":        ligne,
        "arret":        arret or "",
        "heure_alerte": heure_alerte,
        "actif":        True
    }).execute()
    return res.data[0]


def get_abonnements_proactifs(avant_minutes: int = 15) -> list[dict]:
    """Abonnés dont l'heure habituelle approche dans X minutes."""
    db = get_client()
    heure_cible = (datetime.now(timezone.utc) + timedelta(minutes=avant_minutes)).strftime("%H:%M")
    res = (db.table("abonnements")
             .select("*")
             .eq("actif", True)
             .eq("heure_alerte", heure_cible)
             .execute())
    return res.data or []


# ── Tickets (escalade) ────────────────────────────────────

def create_ticket(phone: str, motif: str) -> dict:
    db = get_client()
    res = db.table("tickets").insert({
        "phone":    phone,
        "motif":    motif,
        "priorite": "normale",
        "statut":   "ouvert"
    }).execute()
    return res.data[0]


# ── Lignes ────────────────────────────────────────────────

def get_all_lignes() -> list[dict]:
    db = get_client()
    res = db.table("lignes").select("*").eq("actif", True).execute()
    return res.data or []


def ligne_existe(numero: str) -> bool:
    db = get_client()
    res = db.table("lignes").select("id").eq("numero", numero).execute()
    return bool(res.data)


# ── Sessions ──────────────────────────────────────────────

SESSION_CONTEXT_TTL_SECONDS = 600  # 10 min


def get_session(phone: str) -> dict | None:
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
    res = db.table("sessions").upsert(data, on_conflict="phone").execute()
    return res.data[0]


def delete_session(phone: str):
    db = get_client()
    db.table("sessions").delete().eq("phone", phone).execute()


def purge_sessions_expires():
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()
    db.table("sessions").delete().lt("expires_at", now).execute()


# ── Network memory ────────────────────────────────────────

def get_network_memory() -> list[dict]:
    """Retourne les données de ponctualité par ligne (pour Dead Reckoning)."""
    db = get_client()
    res = db.table("network_memory").select("*").execute()
    return res.data or []


# ── Horaires théoriques (Phase 3) ─────────────────────────

def save_schedules_batch(schedules: list[dict]):
    """
    Insère ou met à jour les horaires scrappés en masse.
    Structure attendue : { ligne, arret, heure_passage, jour_semaine }
    """
    db = get_client()
    try:
        db.table("schedules").upsert(schedules).execute()
        logger.info(f"✅ {len(schedules)} horaires insérés/mis à jour.")
    except Exception as e:
        logger.error(f"❌ save_schedules_batch: {e}")


def get_next_theoretical_bus(ligne: str, arret: str, limit: int = 3) -> list[dict]:
    """
    Récupère les prochains passages théoriques pour une ligne/arrêt
    à partir de l'heure actuelle (UTC).
    """
    db = get_client()
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    res = (db.table("schedules")
             .select("heure_passage, arret, ligne")
             .eq("ligne", ligne)
             .ilike("arret", f"%{arret}%")
             .gte("heure_passage", now_time)
             .order("heure_passage", desc=False)
             .limit(limit)
             .execute())
    return res.data or []


def get_first_departure(ligne: str) -> str | None:
    """Premier départ de la journée pour une ligne (Dead Reckoning)."""
    db = get_client()
    res = (db.table("schedules")
             .select("heure_passage")
             .eq("ligne", ligne)
             .order("heure_passage", desc=False)
             .limit(1)
             .execute())
    if res.data:
        return res.data[0]["heure_passage"]
    return None


# ── API Leaderboard ───────────────────────────────────────

def get_leaderboard(limit: int = 10) -> list[dict]:
    """
    Top signaleurs du mois — triés par nb_signalements DESC.

    ⚠️ DETTE TECHNIQUE : charge les messages en mémoire Python.
    À migrer vers RPC Supabase avant 50k signalements.
    """
    db = get_client()
    un_mois = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    res = (db.table("messages")
             .select("conversations(contacts(phone, fiabilite_score))")
             .eq("intent", "signalement")
             .eq("role", "user")
             .gte("created_at", un_mois)
             .execute())

    compteur: dict[str, dict] = {}
    for row in (res.data or []):
        try:
            contact = row["conversations"]["contacts"]
            phone   = contact["phone"]
            score   = contact.get("fiabilite_score", 0.5)
            if phone not in compteur:
                compteur[phone] = {
                    "phone":           phone,
                    "fiabilite_score": score,
                    "nb_signalements": 0,
                }
            compteur[phone]["nb_signalements"] += 1
        except (KeyError, TypeError):
            continue

    return sorted(compteur.values(),
                  key=lambda x: x["nb_signalements"],
                  reverse=True)[:limit]


def get_stats_communaute() -> dict:
    """Stats globales : signalements aujourd'hui, all time, nb contributeurs."""
    db = get_client()
    today_start = datetime.combine(
        date.today(), datetime.min.time()
    ).replace(tzinfo=timezone.utc).isoformat()

    res_today = (db.table("signalements")
                   .select("id", count="exact")
                   .gte("timestamp", today_start)
                   .execute())

    res_all = (db.table("messages")
                 .select("id", count="exact")
                 .eq("intent", "signalement")
                 .eq("role", "user")
                 .execute())

    res_contacts = (db.table("contacts")
                      .select("id", count="exact")
                      .execute())

    return {
        "aujourd_hui":      res_today.count or 0,
        "all_time":         res_all.count or 0,
        "nb_contributeurs": res_contacts.count or 0,
    }