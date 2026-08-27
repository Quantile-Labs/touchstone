# Fonts

The faces this site is set in, the same files quantilelabs.com serves, so the two sites
render identically.

| File | Family | Licence |
|---|---|---|
| `plex-mono-400.woff2` | IBM Plex Mono, regular | SIL Open Font License 1.1, see `IBM-Plex-OFL.txt` |
| `plex-mono-500.woff2` | IBM Plex Mono, medium | SIL Open Font License 1.1, see `IBM-Plex-OFL.txt` |
| `google-sans-flex.woff2` | Google Sans Flex, latin | Google's brand typeface |
| `google-sans-flex-ext.woff2` | Google Sans Flex, latin extended | Google's brand typeface |

The IBM Plex files are redistributable under the OFL, whose text has to travel with them
and does, in this directory.

**The Google Sans Flex files are a different case and a reader should know it.** Google
Sans is Google's own brand family and is not published on Google Fonts under an open
licence. They are here because this site is set in what the laboratory site is set in, and
that was a decision taken with the position understood. Anyone forking this repository and
publishing the result is making the same decision for themselves, and should check it
rather than inheriting it.

`docs/assets/css/quantile.css` names `ui-sans-serif, system-ui, sans-serif` as the fallback
on every stack, so deleting the two Google Sans files leaves a site that builds and reads
correctly in the platform's own grotesque.
