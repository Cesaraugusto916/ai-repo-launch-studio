# Diretrizes do Projeto Portfolio Video Hub

## Regra Fundamental para Síntese de Voz (TTS) com Google GenAI
Nos modelos de síntese de voz (TTS) do Google Gemini (ex: `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-2.5-flash-tts`):
1. **O campo `contents` é lido e vocalizado literalmente na íntegra.**
2. **NUNCA** inclua diretrizes de atuação, prompts ou metainstruções dentro de `contents` (como *"Fale com clareza..."*, *"Instruções para o locutor:"*, *"Tom persuasivo:"*). Qualquer instrução inserida em `contents` será sintetizada como fala no áudio final.
3. O campo `contents` deve conter **exclusivamente o texto puro do roteiro** a ser falado pelo narrador.
4. Para ajustar tom e ritmo, module a pontuação do próprio texto (vírgulas para pausas cadenciadas, pontos finais para conclusões firmes, travessões para ênfase).
