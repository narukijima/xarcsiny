<p align="center"><a href="https://xarcsiny.com"><img src="https://xarcsiny.com/assets/og/home.png" alt="x=arcsin y" width="640"></a></p>

<p align="center"><b>Every equation has a sound.</b><br><a href="https://xarcsiny.com">xarcsiny.com</a></p>

x=arcsin y is a music project. Each track takes one equation and lets it drive the part you remember: a melody, a rhythm, the way an echo falls.

To hear it, go to [xarcsiny.com](https://xarcsiny.com). You can tap an equation and it plays, and every score moves along with the sound. This repository is the code behind that site, along with the words about each equation.

## Made with AI

AI composes the tracks and writes the code. The code calculates every sample. There are no recordings, no sample packs and no human voice; the choirs and accordions are arithmetic too. A person listens and decides what stays.

```
Math × Music × Code × AI = Math Sound

label  y=sin(x)
artist x=arcsin y
prod.  Naru Kijima
```

## What's here

| | |
|---|---|
| `src/`, `worker.js` | The site as it runs: pages' script and style, audio byte ranges on Cloudflare Workers |
| `tools/` | The static site generator, and `score_xml.py`, which turns notes into readable notation and MIDI |
| `content/` | What each equation decides, what was composed, and the site's pages |
| `data/` | The track list and store links |
| `scripts/` | The check that keeps this repository clean |

## What isn't here

The audio, the score files and the code that makes the sound. The album is registered with audio matching systems such as Content ID, which require exclusive rights, so anything that could regenerate the sound stays private. The scores themselves are free to read and download on [the site](https://xarcsiny.com/scores/).

That also means this repository can't build the site by itself: `tools/` reads those private inputs from a local file (`tools/paths.py`).

## License

- **The site's code** is under the [MIT license](LICENSE).
- **The music, the scores and the words about them** aren't. They follow the [terms](https://xarcsiny.com/terms/), and this isn't a Creative Commons, open or royalty-free license.
- **The Inter font** is under the [SIL Open Font License](src/fonts/OFL.txt).

[LICENSE](LICENSE) lists which path is which.

## Contact

[contact@xarcsiny.com](mailto:contact@xarcsiny.com)
