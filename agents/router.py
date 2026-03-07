from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

INTENTS = {
    "question":   "Question d'information générale",
    "complaint":  "Réclamation ou insatisfaction",
    "order":      "Commande ou suivi de commande",
    "purchase":   "Intention d'achat ou demande de prix",
    "escalate":   "Demande explicite d'un agent humain",
    "out_of_scope": "Hors sujet"
}

async def classify_intent(text: str, language: str = "fr") -> dict:
    """Classifie l'intention du message client"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Tu es un classificateur d'intentions pour un service client africain.
Réponds UNIQUEMENT avec ce format JSON exact :
{"intent": "CODE", "confidence": 0.XX}

Codes disponibles :
- question : demande d'information
- complaint : réclamation, problème, insatisfaction
- order : suivi ou modification de commande
- purchase : achat, prix, disponibilité produit
- escalate : demande explicite d'un humain
- out_of_scope : hors sujet

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

        import json
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
