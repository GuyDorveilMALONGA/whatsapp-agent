"""
memory/network_memory.py — V2
Mémoire réseau distillée : patterns de ponctualité par ligne/segment/heure.
Après 3 mois, Sëtu connaît le Bus 15 mieux que Dem Dikk elle-même.

Structure table network_memory :
  ligne_id, segment, heure (ex: "07"), jour_semaine (0=lundi)
  ponctualite FLOAT, intervalle_moyen_min INT, nb_observations INT, note TEXT
"""
import logging
from datetime import datetime, timezone

from db.client import get_client

logger = logging.getLogger(__name__)


def get_eta_prediction(ligne: str, arret_depart: str | None = None) -> dict | None:
    """
    Retourne une prédiction ETA pour une ligne à l'heure actuelle.
    Utilisé par context_builder pour enrichir le contexte LLM.

    Retourne :
      {
        "intervalle_moyen_min": 14,
        "ponctualite": 0.82,
        "note": "vendredi 16h-18h perturbé — marché Tilène",
        "nb_observations": 230
      }
    """
    try:
        db = get_client()
        now = datetime.now(timezone.utc)
        heure = now.strftime("%H")
        jour = str(now.weekday())   # 0=lundi ... 6=dimanche

        # Cherche d'abord avec segment + heure + jour
        res = (db.table("network_memory")
                 .select("*")
                 .eq("ligne_id", ligne)
                 .eq("heure", heure)
                 .eq("jour_semaine", jour)
                 .order("nb_observations", desc=True)
                 .limit(1)
                 .execute())

        if res.data:
            r = res.data[0]
            return {
                "intervalle_moyen_min": r.get("intervalle_moyen_min"),
                "ponctualite": r.get("ponctualite"),
                "note": r.get("note"),
                "nb_observations": r.get("nb_observations"),
            }

        # Fallback : juste heure (tous jours)
        res2 = (db.table("network_memory")
                  .select("*")
                  .eq("ligne_id", ligne)
                  .eq("heure", heure)
                  .order("nb_observations", desc=True)
                  .limit(1)
                  .execute())

        if res2.data:
            r = res2.data[0]
            return {
                "intervalle_moyen_min": r.get("intervalle_moyen_min"),
                "ponctualite": r.get("ponctualite"),
                "note": r.get("note"),
                "nb_observations": r.get("nb_observations"),
            }

        return None

    except Exception as e:
        logger.error(f"[NetworkMemory] get_eta_prediction: {e}")
        return None


def upsert_memory_entry(
    ligne_id: str,
    segment: str,
    heure: str,
    jour_semaine: int,
    intervalle_min: float,
    ponctuel: bool,
):
    """
    Met à jour ou crée une entrée mémoire réseau.
    Appelé par daily_distiller après agrégation des signalements.
    """
    try:
        db = get_client()

        # Cherche entrée existante
        res = (db.table("network_memory")
                 .select("*")
                 .eq("ligne_id", ligne_id)
                 .eq("segment", segment)
                 .eq("heure", heure)
                 .eq("jour_semaine", str(jour_semaine))
                 .execute())

        if res.data:
            existing = res.data[0]
            n = existing["nb_observations"]
            # Mise à jour incrémentale (moyenne glissante)
            new_intervalle = (existing["intervalle_moyen_min"] * n + intervalle_min) / (n + 1)
            new_ponctualite = (existing["ponctualite"] * n + (1 if ponctuel else 0)) / (n + 1)

            db.table("network_memory").update({
                "intervalle_moyen_min": round(new_intervalle, 1),
                "ponctualite": round(new_ponctualite, 3),
                "nb_observations": n + 1,
            }).eq("id", existing["id"]).execute()

        else:
            db.table("network_memory").insert({
                "ligne_id": ligne_id,
                "segment": segment,
                "heure": heure,
                "jour_semaine": str(jour_semaine),
                "intervalle_moyen_min": round(intervalle_min, 1),
                "ponctualite": 1.0 if ponctuel else 0.0,
                "nb_observations": 1,
            }).execute()

    except Exception as e:
        logger.error(f"[NetworkMemory] upsert_memory_entry: {e}")


def format_for_context(eta: dict | None) -> str:
    """
    Formate la prédiction ETA pour injection dans le context_builder.
    """
    if not eta:
        return ""

    parts = []
    if eta.get("intervalle_moyen_min"):
        parts.append(f"Intervalle moyen: ~{eta['intervalle_moyen_min']} min")
    if eta.get("ponctualite") is not None:
        parts.append(f"Ponctualité historique: {eta['ponctualite']:.0%}")
    if eta.get("note"):
        parts.append(f"Note: {eta['note']}")
    if eta.get("nb_observations"):
        parts.append(f"(basé sur {eta['nb_observations']} observations)")

    return "[MÉMOIRE RÉSEAU] " + " | ".join(parts) if parts else ""
