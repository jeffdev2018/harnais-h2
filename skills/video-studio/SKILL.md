---
name: video-studio
description: Harnais Production Vidéo & Shorts (Avelis_evo1 / HyperFrames / RAEA) avec Mode Cuisine sur words.json/transcript.json et Juge média ffprobe chmod 444.
---

# Harnais Video-Studio — Shorts, Reels & HyperFrames

1. **Transcripts & Timings en Mode Cuisine** :
   - Ne lis jamais `words.json`, `transcript.json` ou `raea.lock` en entier dans le chat.
   - Utilise `python3 harnais-h2/cuisine/cuisine_repl.py peek <fichier>` ou interroge-les en Python (`query`).
2. **Preuve de rendu avant arrêt (`judge_video.py` en `chmod 444`)** :
   - Tout `.mp4` ou `.wav` généré doit être vérifié par `ffprobe` (taille > 10 Ko, durée > 0.5s).
   - Toute planche contact (`dod_contact_sheet.png`) doit exister et faire > 5 Ko avant de conclure.

## Cas limites appris (patcher 1 ligne par erreur réelle)
- `[Patch #1]` (UNIQUEMENT SI applicable à la consigne) : Toujours vérifier que `short.html` / `index.html` se ferme proprement par `</html>` avant le rendu.
