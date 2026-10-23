# Avisos de terceiros

O código do Voice Notes é distribuído sob a [licença MIT](LICENSE). O instalador para Windows inclui componentes de terceiros, que continuam regidos pelas suas próprias licenças, listadas abaixo. Os textos completos das licenças acompanham cada pacote e estão disponíveis nos links indicados.

## Componentes incluídos no instalador

| Componente | Licença | Projeto |
|---|---|---|
| CustomTkinter | MIT | https://github.com/TomSchimansky/CustomTkinter |
| faster-whisper | MIT | https://github.com/SYSTRAN/faster-whisper |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| pyannote.audio | MIT | https://github.com/pyannote/pyannote-audio |
| PyTorch / torchaudio | BSD-3-Clause (e outras permissivas) | https://github.com/pytorch/pytorch |
| NumPy | BSD-3-Clause | https://github.com/numpy/numpy |
| PyAV | BSD-3-Clause | https://github.com/PyAV-Org/PyAV |
| PyAudioWPatch | Apache-2.0 | https://github.com/s0d3s/PyAudioWPatch |
| Pillow | MIT-CMU | https://github.com/python-pillow/Pillow |
| keyring | MIT | https://github.com/jaraco/keyring |
| python-docx | MIT | https://github.com/python-openxml/python-docx |
| ReportLab | BSD | https://www.reportlab.com/ |
| Send2Trash | BSD-3-Clause | https://github.com/arsenetar/send2trash |
| imageio-ffmpeg | BSD-2-Clause | https://github.com/imageio/imageio-ffmpeg |
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp |
| lameenc | LGPL-3.0-or-later | https://github.com/chrisstaite/lameenc |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| Python | PSF License | https://www.python.org/ |
| PyInstaller (bootloader) | GPL-2.0-or-later com exceção de bootloader | https://github.com/pyinstaller/pyinstaller |

## Observações

- **Bibliotecas LGPL (lameenc, pystray):** são usadas sem modificação, como módulos separados dentro da pasta de instalação, e podem ser substituídas por outras versões compatíveis. O código-fonte está disponível nos links acima.
- **FFmpeg:** o pacote imageio-ffmpeg traz um executável do FFmpeg, chamado como processo separado. Esse binário é distribuído sob a licença GPL do próprio FFmpeg; o código-fonte está em https://ffmpeg.org/ e em https://github.com/imageio/imageio-binaries.
- **Bibliotecas NVIDIA CUDA (cuBLAS, cuDNN, NVRTC):** redistribuídas sob o contrato de licença da NVIDIA. As licenças acompanham o instalador em `licenses\NVIDIA`.
- **Modelos de IA:** os modelos Whisper e o modelo de separação de falantes não são incluídos no instalador. Eles são baixados no primeiro uso, e o modelo `pyannote/speaker-diarization-community-1` exige que o próprio usuário aceite os termos no Hugging Face.
- **Codex CLI e Claude Code:** quando instalados pela opção do instalador, são baixados diretamente das fontes oficiais e seguem os termos dos respectivos fornecedores.
