"""
db/queries.py — V5.7
Règle absolue : SEUL fichier qui touche Supabase.

MIGRATIONS V5.7 depuis V5.6 :
  - AJOUT : get_session(), set_session(), delete_session()
    Manquaient → session_manager plantait → "Spécialisé bus Dem Dikk" sur toutes les questions
  - AJOUT : get_leaderboard(), get_stats_communaute()
    Manquaient → /api/leaderboard retournait 500
"""
from datetime import datetime, timedelta, timezone, date
import logging
from db.client import get_client
from config.settings import SIGNALEMENT_TTL_MINUTES, DEDUP_ARRET_WINDOW_MIN

logger = logging.getLogger(__name__)

DEDUP_WINDOW_SECONDS = 120  # 2 minutes — doublon strict même phone


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


def count_messages(conversation_id: str) -> int:
    db = get_client()
    try:
        res = (db.table("messages")
                 .select("id", count="exact")
                 .eq("conversation_id", conversation_id)
                 .execute())
        return res.count or 0
    except Exception as e:
        logger.error(f"[count_messages] conv_id={conversation_id} — erreur: {e}")
        return 1


# ── Sessions ──────────────────────────────────────────────

def get_session(phone: str) -> dict | None:
    """Récupère la session active pour ce phone. Retourne None si absente ou expirée."""
    db  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    try:
        res = (db.table("sessions")
                 .select("*")
                 .eq("phone", phone)
                 .gt("expires_at", now)
                 .order("created_at", desc=True)
                 .limit(1)
                 .execute())
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"[get_session] phone={phone[-4:]} erreur: {e}")
        return None


def set_session(phone: str,
                etat: str | None = None,
                ligne: str | None = None,
                destination: str | None = None,
                signalement: dict | None = None,
                ttl_seconds: int = 1800):
    """Crée ou met à jour la session pour ce phone (upsert sur phone)."""
    import json
    db         = get_client()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    row = {
        "phone":      phone,
        "etat":       etat,
        "ligne":      ligne,
        "destination": destination,
        "signalement": signalement,
        "expires_at": expires_at,
    }
    try:
        # Tente upsert sur phone
        db.table("sessions").upsert(row, on_conflict="phone").execute()
        logger.debug(f"[set_session] {phone[-4:]} etat={etat} ligne={ligne}")
    except Exception as e:
        logger.error(f"[set_session] phone={phone[-4:]} erreur: {e}")
        raise


def delete_session(phone: str):
    """Supprime la session de ce phone."""
    db = get_client()
    try:
        db.table("sessions").delete().eq("phone", phone).execute()
        logger.debug(f"[delete_session] {phone[-4:]} supprimée")
    except Exception as e:
        logger.error(f"[delete_session] phone={phone[-4:]} erreur: {e}")


# ── Signalements ──────────────────────────────────────────

def is_signalement_doublon(ligne: str, arret: str, phone: str) -> bool:
    db    = get_client()
    now   = datetime.now(timezone.utc)
    since = (now - timedelta(seconds=DEDUP_WINDOW_SECONDS)).isoformat()
    try:
        res = (db.table("signalements")
                 .select("id")
                 .eq("ligne", ligne)
                 .eq("position", arret)
                 .eq("phone", phone)
                 .gte("timestamp", since)
                 .limit(1)
                 .execute())
        return bool(res.data)
    except Exception as e:
        logger.error(f"[dedup] Erreur check doublon strict: {e}")
        return False


def is_signalement_arret_recent(ligne: str, arret: str) -> bool:
    db    = get_client()
    now   = datetime.now(timezone.utc)
    since = (now - timedelta(minutes=DEDUP_ARRET_WINDOW_MIN)).isoformat()
    try:
        res = (db.table("signalements")
                 .select("id")
                 .eq("ligne", ligne)
                 .eq("position", arret)
                 .gte("timestamp", since)
                 .limit(1)
                 .execute())
        return bool(res.data)
    except Exception as e:
        logger.error(f"[dedup_arret] Erreur check communautaire: {e}")
        return False


def save_signalement(ligne: str, arret: str, phone: str,
                     lat: float | None = None,
                     lon: float | None = None) -> dict | None:
    if is_signalement_doublon(ligne, arret, phone):
        logger.info(f"[Dedup] Doublon strict — {phone[-4:]} ligne={ligne} arret={arret}")
        penalise_spam(phone)
        return None

    if is_signalement_arret_recent(ligne, arret):
        logger.info(f"[Dedup-Arret] Signalement communautaire récent — ligne={ligne} arret={arret!r}")
        return None

    db = get_client()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SIGNALEMENT_TTL_MINUTES)

    row = {
        "ligne":      ligne,
        "position":   arret,
        "phone":      phone,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "valide":     True,
    }
    if lat is not None:
        row["lat"] = lat
    if lon is not None:
        row["lon"] = lon

    try:
        res = db.table("signalements").insert(row).execute()
        return res.data[0]
    except Exception as e:
        if lat is not None or lon is not None:
            logger.warning(f"[save_signalement] Retry sans lat/lon: {e}")
            row.pop("lat", None)
            row.pop("lon", None)
            res = db.table("signalements").insert(row).execute()
            return res.data[0]
        raise


def penalise_spam(phone: str):
    db = get_client()
    try:
        res = (db.table("contacts")
                 .select("fiabilite_score")
                 .eq("phone", phone)
                 .execute())
        if not res.data:
            return
        current   = res.data[0].get("fiabilite_score", 0.5)
        penalised = max(0.10, current * 0.9)
        db.table("contacts").update({
            "fiabilite_score": round(penalised, 3)
        }).eq("phone", phone).execute()
    except Exception as e:
        logger.error(f"[Reliability] Erreur pénalité spam: {e}")


def boost_corroboration(ligne: str, arret: str, phone_confirmateur: str):
    db = get_client()
    try:
        res = (db.table("signalements")
                 .select("phone")
                 .eq("ligne", ligne)
                 .eq("position", arret)
                 .neq("phone", phone_confirmateur)
                 .order("timestamp", desc=True)
                 .limit(1)
                 .execute())
        if not res.data:
            return
        phone_original = res.data[0]["phone"]
        original = (db.table("contacts")
                      .select("fiabilite_score")
                      .eq("phone", phone_original)
                      .execute())
        if not original.data:
            return
        current = original.data[0].get("fiabilite_score", 0.5)
        boosted = min(1.0, current + 0.05)
        db.table("contacts").update({
            "fiabilite_score": round(boosted, 3)
        }).eq("phone", phone_original).execute()
    except Exception as e:
        logger.error(f"[Reliability] Erreur corroboration: {e}")


def get_signalements_actifs(ligne: str) -> list[dict]:
    db  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("signalements")
             .select("*")
             .eq("ligne", ligne)
             .gt("expires_at", now)
             .order("timestamp", desc=True)
             .execute())
    return res.data or []


def get_all_signalements_actifs() -> list[dict]:
    db  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    res = (db.table("signalements")
             .select("*")
             .gt("expires_at", now)
             .order("timestamp", desc=True)
             .execute())
    return res.data or []


def get_derniers_signalements(ligne: str, limit: int = 1) -> list[dict]:
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
    db  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    db.table("signalements").delete().lt("expires_at", now).execute()


def get_derniers_signalements_par_phone(phone: str, ligne: str, limit: int = 1) -> list[dict]:
    db = get_client()
    try:
        res = (db.table("signalements")
                 .select("ligne, position, timestamp")
                 .eq("phone", phone)
                 .eq("ligne", ligne)
                 .order("timestamp", desc=True)
                 .limit(limit)
                 .execute())
        return res.data or []
    except Exception as e:
        logger.error(f"[queries] get_derniers_signalements_par_phone erreur: {e}")
        return []


def get_signalements_recents_par_phone(phone: str, since_iso: str) -> list[dict]:
    db = get_client()
    try:
        res = (db.table("signalements")
                 .select("ligne, position, timestamp")
                 .eq("phone", phone)
                 .gte("timestamp", since_iso)
                 .order("timestamp", desc=True)
                 .execute())
        return res.data or []
    except Exception as e:
        logger.error(f"[queries] get_signalements_recents_par_phone erreur: {e}")
        return []


def get_lignes_silencieuses(seuil_minutes: int) -> list[str]:
    db     = get_client()
    since  = (datetime.now(timezone.utc) - timedelta(minutes=seuil_minutes)).isoformat()
    lignes = db.table("lignes").select("numero").eq("actif", True).execute()
    toutes = {l["numero"] for l in (lignes.data or [])}
    sigs   = (db.table("signalements")
                .select("ligne")
                .gt("timestamp", since)
                .execute())
    actives = {s["ligne"] for s in (sigs.data or [])}
    return list(toutes - actives)


def enrichir_signalement(ligne: str, arret: str, qualite: str, phone: str | None = None) -> bool:
    db = get_client()
    try:
        query = (db.table("signalements")
                   .select("id")
                   .eq("ligne", ligne)
                   .eq("position", arret)
                   .order("timestamp", desc=True)
                   .limit(1))
        res = query.execute()

        if not res.data and phone:
            res_fallback = (db.table("signalements")
                              .select("id")
                              .eq("ligne", ligne)
                              .eq("phone", phone)
                              .order("timestamp", desc=True)
                              .limit(1)
                              .execute())
            if not res_fallback.data:
                return False
            sig_id = res_fallback.data[0]["id"]
        else:
            if not res.data:
                return False
            sig_id = res.data[0]["id"]

        db.table("signalements").update({"qualite": qualite}).eq("id", sig_id).execute()
        return True
    except Exception as e:
        logger.error(f"[enrichir_signalement] Erreur: {e}")
        return False


# ── Signalements GPS ──────────────────────────────────────

def is_recent_gps_signalement(phone: str, window_seconds: int = 30) -> bool:
    db    = get_client()
    now   = datetime.now(timezone.utc)
    since = (now - timedelta(seconds=window_seconds)).isoformat()
    try:
        res = (db.table("signalements")
                 .select("id")
                 .eq("phone", phone)
                 .gte("timestamp", since)
                 .limit(1)
                 .execute())
        return bool(res.data)
    except Exception as e:
        logger.error(f"[gps_antispam] Erreur check: {e}")
        return False


def save_signalement_gps(ligne: str, arret: str, phone: str, ttl_minutes: int = 10) -> dict | None:
    db         = get_client()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    try:
        res = db.table("signalements").insert({
            "ligne":      ligne,
            "position":   arret,
            "phone":      phone,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
            "valide":     True,
            "qualite":    "gps",
        }).execute()
        return res.data[0]
    except Exception as e:
        logger.error(f"[gps] save_signalement_gps erreur: {e}")
        return None


def get_signalements_recents(minutes: int = 5) -> list:
    try:
        db    = get_client()
        since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        res   = (db.table("signalements")
                   .select("*")
                   .gte("timestamp", since)
                   .order("timestamp", desc=True)
                   .execute())
        return res.data or []
    except Exception as e:
        logger.error(f"[queries] get_signalements_recents erreur: {e}")
        return []


# ── Abonnements ───────────────────────────────────────────

def get_abonnes(ligne: str) -> list[dict]:
    db  = get_client()
    res = (db.table("abonnements")
             .select("phone, arret, heure_alerte")
             .eq("ligne", ligne)
             .eq("actif", True)
             .limit(500)
             .execute())
    return res.data or []


def create_abonnement(phone: str, ligne: str, arret: str, heure_alerte: str | None = None) -> dict:
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


def delete_abonnement(phone: str, ligne: str):
    db = get_client()
    db.table("abonnements").update({"actif": False}).eq("phone", phone).eq("ligne", ligne).execute()


def get_abonnements_actifs(phone: str) -> list[dict]:
    db = get_client()
    try:
        res = (db.table("abonnements")
                 .select("ligne")
                 .eq("phone", phone)
                 .eq("actif", True)
                 .execute())
        return res.data or []
    except Exception as e:
        logger.error(f"[queries] get_abonnements_actifs erreur: {e}")
        return []


def deactivate_abonnement(phone: str, ligne: str):
    db = get_client()
    try:
        db.table("abonnements").update({"actif": False}).eq("phone", phone).eq("ligne", ligne).execute()
    except Exception as e:
        logger.error(f"[queries] deactivate_abonnement erreur: {e}")


# ── Push subscriptions ────────────────────────────────────

def save_push_subscription(phone: str, endpoint: str, p256dh: str, auth: str):
    db = get_client()
    try:
        db.table("push_subscriptions").upsert({
            "phone":    phone,
            "endpoint": endpoint,
            "p256dh":   p256dh,
            "auth":     auth,
        }, on_conflict="endpoint").execute()
    except Exception as e:
        logger.error(f"[Push] save_push_subscription erreur: {e}")
        raise


def delete_push_subscription(phone: str, endpoint: str):
    try:
        db = get_client()
        db.table("push_subscriptions").delete().eq("phone", phone).eq("endpoint", endpoint).execute()
    except Exception as e:
        logger.error(f"[Push] delete_push_subscription erreur: {e}")
        raise


def get_push_subscriptions_by_phone(phone: str) -> list:
    try:
        db     = get_client()
        result = db.table("push_subscriptions").select("*").eq("phone", phone).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"[Push] get_push_subscriptions_by_phone erreur: {e}")
        return []


def get_push_subscriptions_by_ligne(ligne: str) -> list:
    try:
        db      = get_client()
        abonnes = (db.table("abonnements")
                     .select("phone")
                     .eq("ligne", ligne)
                     .eq("actif", True)
                     .execute())
        phones = [a["phone"] for a in (abonnes.data or [])]
        if not phones:
            return []
        result = db.table("push_subscriptions").select("*").in_("phone", phones).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"[Push] get_push_subscriptions_by_ligne erreur: {e}")
        return []


# ── Leaderboard ───────────────────────────────────────────

def get_leaderboard(limit: int = 10) -> list[dict]:
    """
    Top signaleurs : joint contacts + compte signalements par phone.
    Retourne une liste triée par nb_signalements DESC.
    """
    db = get_client()
    try:
        # Compte les signalements par phone
        sigs = db.table("signalements").select("phone").execute()
        counts: dict[str, int] = {}
        for s in (sigs.data or []):
            p = s.get("phone", "")
            counts[p] = counts.get(p, 0) + 1

        if not counts:
            return []

        # Récupère les contacts concernés
        phones = list(counts.keys())
        contacts_res = (db.table("contacts")
                          .select("phone, fiabilite_score")
                          .in_("phone", phones)
                          .execute())

        results = []
        for c in (contacts_res.data or []):
            p = c["phone"]
            results.append({
                "phone":            p,
                "nb_signalements":  counts.get(p, 0),
                "fiabilite_score":  c.get("fiabilite_score", 0.5),
            })

        results.sort(key=lambda x: x["nb_signalements"], reverse=True)
        return results[:limit]

    except Exception as e:
        logger.error(f"[get_leaderboard] erreur: {e}")
        return []


def get_stats_communaute() -> dict:
    """Stats globales : signalements aujourd'hui, all time, nb contributeurs."""
    db = get_client()
    try:
        # All time
        all_res  = db.table("signalements").select("id", count="exact").execute()
        all_time = all_res.count or 0

        # Aujourd'hui
        today       = date.today().isoformat()
        today_res   = (db.table("signalements")
                         .select("id", count="exact")
                         .gte("timestamp", today)
                         .execute())
        aujourd_hui = today_res.count or 0

        # Nb contributeurs uniques
        phones_res      = db.table("signalements").select("phone").execute()
        nb_contributeurs = len({s["phone"] for s in (phones_res.data or [])})

        return {
            "all_time":        all_time,
            "aujourd_hui":     aujourd_hui,
            "nb_contributeurs": nb_contributeurs,
        }
    except Exception as e:
        logger.error(f"[get_stats_communaute] erreur: {e}")
        return {"all_time": 0, "aujourd_hui": 0, "nb_contributeurs": 0}