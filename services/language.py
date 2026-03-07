from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

LANGUAGES = {
    "wo": "Wolof",
    "ff": "Pulaar",
    "fr": "Français",
    "en": "Anglais",
    "other": "Autre"
}

async def detect_language(text: str) -> str:
    """Détecte la langue d'un message — retourne le code langue"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """Tu es un détecteur de langue expert pour l'Afrique de l'Ouest.
Réponds UNIQUEMENT avec l'un de ces codes : wo, ff, fr, en, other
- wo = Wolof
- ff = Pulaar/Fula
- fr = Français
- en = Anglais
- other = Autre langue
Ne réponds qu'avec le code, rien d'autre."""
                },
                {
                    "role": "user",
                    "content": f"Quelle est la langue de ce texte : '{text}'"
                }
            ],
            max_tokens=5,
            temperature=0
        )
        lang = response.choices[0].message.content.strip().lower()
        return lang if lang in LANGUAGES else "fr"
    except Exception as e:
        print(f"Erreur détection langue: {e}")
        return "fr"
