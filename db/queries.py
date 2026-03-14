"""
db/queries.py — V5.1
Règle absolue : SEUL fichier qui touche Supabase.

MIGRATIONS V5.1 depuis V5.0 :
  - AJOUT count_messages(conversation_id) — requis par main.py V8.2
    pour détecter la première visite sans charger l'historique complet.
    Utilise count="exact" côté Supabase (pas de transfert de lignes).
"""
from datetime import datetime, timedelta, timezone, date
import logging
from db.client import get_client
from config.settings import SIGNALEMENT_TTL_MINUTES

logger = logging.getLogger(__name__)

DEDUP_WINDOW_SECONDS = 120  # 2 minutes


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
    """
    NOUVEAU V5.1 — Compte le nombre de messages d'une conversation.
    Utilise count="exact" pour éviter de rapatrier les lignes.
    Utilisé par main.py V8.2 pour détecter la première visite :
        if queries.count_messages(conv_id) == 0:
            await send_fn(phone, WELCOME_MESSAGE)
    Fail safe : retourne 1 en cas d'erreur (évite d'envoyer le welcome en boucle).
    """
    db = get_client()
    try:
        res = (db.table("messages")
                 .select("id", count="exact")
                 .eq("conversation_id", conversation_id)
                 .execute())
        return res.count or 0
    except Exception as e:
        logger.error(f"[count_messages] conv_id={conversation_id} — erreur: {e}")
        return 1  # fail safe : on suppose qu'il y a déjà des messages


# ── Signalements ──────────────────────────────────────────

def is_signalement_doublon(ligne: str, arret: str, phone: str) -> bool:
    """
    Retourne True si doublon détecté dans la fenêtre.
    Fail open si Supabase KO.
    """
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
        logger.error(f"[dedup] Erreur check doublon: {e}")
        return False


def save_signalement(ligne: str, arret: str, phone: str) -> dict | None:
    """
    FIX D1 : Anti-doublon via check explicite + insert.
    La race condition TOCTOU est atténuée par la fenêtre de 2 min.
    Pour une protection absolue, ajouter un UNIQUE index côté Supabase :
      CREATE UNIQUE INDEX idx_signalement_dedup
      ON signalements (ligne, position, phone, (timestamp::date));
    """
    if is_signalement_doublon(ligne, arret, phone):
        logger.info(f"[Dedup] Doublon ignoré — {phone[-4:]} ligne={ligne} arret={arret}")
        penalise_spam(phone)
        return None

    db = get_client()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SIGNALEMENT_TTL_MINUTES)
    res = db.table("signalements").insert({
        "ligne":      ligne,
        "position":   arret,
        "phone":      phone,
        "expires_at": expires_at.isoformat()
    }).execute()
    return res.data[0]


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
        logger.info(f"[Reliability] Spam pénalisé {phone[-4:]}: {current:.2f} → {penalised:.2f}")
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
        original_phone = res.data[0]["phone"]

        contact_res = (db.table("contacts")
                         .select("fiabilite_score, profil_json")
                         .eq("phone", original_phone)
                         .execute())
        if not contact_res.data:
            return

        current = contact_res.data[0].get("fiabilite_score", 0.5)
        profil  = contact_res.data[0].get("profil_json") or {}

        old_rate = profil.get("corroboration_rate", 0.5)
        profil["corroboration_rate"] = min(1.0, old_rate + 0.05)

        boosted = min(1.0, current * 1.05)
        db.table("contacts").update({
            "fiabilite_score": round(boosted, 3),
            "profil_json":     profil,
        }).eq("phone", original_phone).execute()
        logger.info(
            f"[Reliability] Corroboration boost {original_phone[-4:]}: "
            f"{current:.2f} → {boosted:.2f}"
        )
    except Exception as e:
        logger.error(f"[Reliability] Erreur boost corroboration: {e}")


def enrichir_signalement(ligne: str, arret: str, qualite: str, phone: str) -> bool:
    db  = get_client()
    now = datetime.now(timezone.utc).isoformat()

    try:
        res = (db.table("signalements")
                 .select("id")
                 .eq("ligne", ligne)
                 .eq("position", arret)
                 .eq("phone", phone)
                 .gt("expires_at", now)
                 .order("timestamp", desc=True)
                 .limit(1)
                 .execute())

        if not res.data:
            res_fallback = (db.table("signalements")
                              .select("id")
                              .eq("ligne", ligne)
                              .eq("position", arret)
                              .eq("phone", phone)
                              .order("timestamp", desc=True)
                              .limit(1)
                              .execute())
            if not res_fallback.data:
                logger.warning(
                    f"[enrichir_signalement] Aucun signalement trouvé "
                    f"ligne={ligne} arret={arret} phone={phone}"
                )
                return False
            sig_id = res_fallback.data[0]["id"]
        else:
            sig_id = res.data[0]["id"]

        db.table("signalements").update({"qualite": qualite}).eq("id", sig_id).execute()
        logger.info(
            f"[enrichir_signalement] ligne={ligne} arret={arret} "
            f"qualite='{qualite}' → signalement {sig_id} mis à jour"
        )
        return True

    except Exception as e:
        logger.error(f"[enrichir_signalement] Erreur: {e}")
        return False


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


def get_derniers_signalements_par_phone(
    phone: str, ligne: str, limit: int = 1
) -> list[dict]:
    """
    RED TEAM : Retourne les derniers signalements d'un usager sur une ligne.
    Utilisé par anti_fraud.check_distance_coherence().
    """
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
    """
    RED TEAM : Retourne tous les signalements d'un usager depuis un timestamp.
    Utilisé par anti_fraud.is_spam_pattern().
    """
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


# ── Abonnements ───────────────────────────────────────────

def get_abonnes(ligne: str) -> list[dict]:
    """FIX D4 : Paginé — max 500 résultats par sécurité."""
    db  = get_client()
    res = (db.table("abonnements")
             .select("phone, arret, heure_alerte")
             .eq("ligne", ligne)
             .eq("actif", True)
             .limit(500)
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
    """Ancienne version — gardée pour compatibilité."""
    db          = get_client()
    heure_cible = (datetime.now(timezone.utc) + timedelta(minutes=avant_minutes)).strftime("%H:%M")
    res         = (db.table("abonnements")
                     .select("*")
                     .eq("actif", True)
                     .eq("heure_alerte", heure_cible)
                     .execute())
    return res.data or []


def get_abonnements_proactifs_heure(heure: str) -> list[dict]:
    """
    FIX H2 : Prend une heure exacte en paramètre.
    Appelé par heartbeat avec chaque minute de la fenêtre.
    """
    db  = get_client()
    res = (db.table("abonnements")
             .select("*")
             .eq("actif", True)
             .eq("heure_alerte", heure)
             .execute())
    return res.data or []


# ── Tickets (escalade) ────────────────────────────────────

def create_ticket(phone: str, motif: str) -> dict:
    db  = get_client()
    res = db.table("tickets").insert({
        "phone":    phone,
        "motif":    motif,
        "priorite": "normale",
        "statut":   "ouvert"
    }).execute()
    return res.data[0]


# ── Lignes ────────────────────────────────────────────────

def get_all_lignes() -> list[dict]:
    db  = get_client()
    res = db.table("lignes").select("*").eq("actif", True).execute()
    return res.data or []


def ligne_existe(numero: str) -> bool:
    db  = get_client()
    res = db.table("lignes").select("id").eq("numero", numero).execute()
    return bool(res.data)


# ── Sessions ──────────────────────────────────────────────

SESSION_CONTEXT_TTL_SECONDS = 1800  # 30 min


def get_session(phone: str) -> dict | None:
    db  = get_client()
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
    db         = get_client()
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
    db  = get_client()
    now = datetime.now(timezone.utc).isoformat()
    db.table("sessions").delete().lt("expires_at", now).execute()


# ── Network memory ────────────────────────────────────────

def get_network_memory() -> list[dict]:
    db  = get_client()
    res = db.table("network_memory").select("*").execute()
    return res.data or []


# ── Horaires théoriques ───────────────────────────────────

def save_schedules_batch(schedules: list[dict]):
    db = get_client()
    try:
        db.table("schedules").upsert(schedules).execute()
        logger.info(f"✅ {len(schedules)} horaires insérés/mis à jour.")
    except Exception as e:
        logger.error(f"❌ save_schedules_batch: {e}")


def get_next_theoretical_bus(ligne: str, arret: str, limit: int = 3) -> list[dict]:
    db       = get_client()
    now_time = datetime.now(timezone.utc).strftime("%H:%M")
    res      = (db.table("schedules")
                  .select("heure_passage, arret, ligne")
                  .eq("ligne", ligne)
                  .ilike("arret", f"%{arret}%")
                  .gte("heure_passage", now_time)
                  .order("heure_passage", desc=False)
                  .limit(limit)
                  .execute())
    return res.data or []


def get_first_departure(ligne: str) -> str | None:
    db  = get_client()
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
    Top signaleurs du mois.
    ⚠️ TODO : migrer vers RPC Supabase (GROUP BY côté DB).
    """
    db      = get_client()
    un_mois = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    res     = (db.table("messages")
                 .select("conversations(contacts(phone, fiabilite_score))")
                 .eq("intent", "signalement")
                 .eq("role", "user")
                 .gte("created_at", un_mois)
                 .limit(5000)  # FIX D2 : cap pour éviter le timeout
                 .execute())

    compteur: dict[str, dict] = {}
    for row in (res.data or []):
        try:
            contact = row["conversations"]["contacts"]
            phone   = contact["phone"]
            score   = contact.get("fiabilite_score", 0.5)
            if phone not in compteur:
                compteur[phone] = {
                    "phone":           phone[-4:],  # FIX S6 : masquer le phone
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
    db          = get_client()
    today_start = datetime.combine(
        date.today(), datetime.min.time()
    ).replace(tzinfo=timezone.utc).isoformat()

    res_today = (db.table("signalements")
                   .select("id", count="exact")
                   .gte("timestamp", today_start)
                   .execute())
    res_all   = (db.table("messages")
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