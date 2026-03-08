from groq import Groq
import os
import json

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

INTENTS = {
    "signalement":  "Signalement de position d'un bus",
    "question":     "Demande d'information sur un bus ou un trajet",
    "abonnement":   "Abonnement à une ligne ou arrêt",
    "complaint":    "Réclamation ou insatisfaction",
    "escalate":     "Demande explicite d'un agent humain",
    "out_of_scope": "Hors sujet transport"
}


async def classify_intent(text: str, language: str = "fr") -> dict:
    """Classifie l'intention du message — spécialisé transport Dakar"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Tu es un classificateur d'intentions pour Sëtu — agent transport WhatsApp à Dakar.
Réponds UNIQUEMENT avec ce format JSON exact :
{"intent": "CODE", "confidence": 0.XX}

Codes disponibles :
- signalement : l'utilisateur indique où est un bus en ce moment
  (ex: "Bus 15 à Liberté 5", "Le 27 vient de passer Sandaga", "Je suis dans le 10 on est à Pompiers")
- question : demande d'info sur un bus, arrêt ou trajet
  (ex: "Le bus 15 est où ?", "Comment aller au Plateau ?", "Le bus 27 passe à quelle heure ?")
- abonnement : veut être alerté pour une ligne
  (ex: "Préviens-moi pour le 15", "Je prends le 27 chaque matin depuis Liberté 5")
- complaint : problème, insatisfaction, plainte
- escalate : demande explicite d'un humain
- out_of_scope : hors sujet transport

La confidence est entre 0.0 et 1.0.
Ne réponds qu'avec le JSON, rien d'autre."""
                },
                {
                    "role": "user",
                    "content": f"Message : '{text}'"
                }
            ],
            max_tokens=50,
            temperature=0
        )
        result = json.loads(response.choices[0].message.content.strip())
        return result

    except Exception as e:
        print(f"Erreur classification: {e}")
        return {"intent": "question", "confidence": 0.5}


def should_escalate(intent: str, confidence: float) -> bool:
    """Détermine si on doit escalader vers un humain"""
    if intent == "escalate":
        return True
    if intent == "complaint" and confidence > 0.85:
        return True
    if confidence < 0.4:
        return True
    return False
