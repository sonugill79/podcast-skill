# Voices

The 54 voices in the pinned kokoro v1.0 pack, and which to reach for. **Pace, pitch and level below are
measured**, not impressions: every voice read the same 21-word sentence at speed 1.0, and the numbers come from
that audio. The character notes are inference from those measurements plus a listen — correct them freely.

Regenerate the measurements and a listening audition at any time:

```bash
python3 SCRIPTS/audition.py            # writes audition.mp3 + voices.json
python3 SCRIPTS/audition.py --grep am_ # just the American male voices
```

## How to read the numbers

- **Pitch (Hz)** — median fundamental. 85–120 reads as a deep male voice, 120–160 as mid, 160–210 as high.
  Two speakers in one episode want **at least 30 Hz** between them, or an accent difference, or both.
- **Pace (wpm)** — the voice's own speed at 1.0, before any `@ speed` in a cast. The median is **187**. This is
  the single most useful column: a voice 60 wpm off the median has a temperament whether you wanted one or not.
- **Level (dB RMS)** — loudness before `loudnorm` evens it out. It still matters: a quiet voice gets pulled up
  along with its noise floor, so very low numbers mean a hissier episode.

## English voices

`a` = American, `b` = British; `f` = female, `m` = male.

| Voice | Pitch | Pace | Level | Use it for |
|---|---|---|---|---|
| `af_alloy` | 143 | 180 | -22.6 | Analyst, second chair. Measured, slightly flat. |
| `af_aoede` | 182 | 189 | -17.6 | **Strong default host.** Loudest of the set, mid-pitch, easy over an hour. |
| `af_bella` | 200 | 180 | -21.1 | Warm solo narrator — explainers, lifestyle, wellbeing. |
| `af_heart` | 197 | 188 | -22.4 | Two-host default. Bright and friendly. |
| `af_jessica` | 209 | 204 | -22.2 | Short news bulletins. High and fast; tiring past 20 minutes. |
| `af_kore` | 148 | 174 | -18.3 | **Skeptic / analyst.** Low, unhurried, credible. |
| `af_nicole` | 157 | 120 | -22.7 | **Sleep stories, meditation, wind-down.** 120 wpm. Never a debate. |
| `af_nova` | 158 | 188 | -26.9 | Avoid for long-form — 5.7 dB quiet, so normalising lifts its noise. |
| `af_river` | 178 | 208 | -21.6 | Brisk headlines. Fastest voice here; poor for dense material. |
| `af_sarah` | 188 | 188 | -21.0 | Safe co-host. Median everything. |
| `af_sky` | 162 | 184 | -24.1 | Intimate solo. Understated and quiet. |
| `am_adam` | 117 | 187 | -18.3 | **Best all-round male.** Advocate or lead host. |
| `am_echo` | 105 | 189 | -22.6 | Deep neutral narrator — documentary, tech explainer. |
| `am_eric` | 157 | 205 | -21.2 | Energetic co-host. High for a male voice, fast. |
| `am_fenrir` | 135 | 183 | -19.1 | Opinion and sports-talk energy. Punchy, loud. |
| `am_liam` | 121 | 199 | -21.7 | Casual interview. Conversational and quick. |
| `am_michael` | 114 | 167 | -24.0 | Two-host default. Measured, a touch quiet. |
| `am_onyx` | 87 | 184 | -23.1 | **Authority.** True crime, documentary, gravitas. |
| `am_puck` | 108 | 178 | -18.9 | Storytelling. Low and characterful. |
| `am_santa` | 142 | 173 | -22.9 | Novelty only. |
| `bf_alice` | 205 | 186 | -20.4 | Culture and arts. Crisp, high British. |
| `bf_emma` | 182 | 205 | -20.5 | Lively presenter. Fastest British — pair with slower voices. |
| `bf_isabella` | 198 | 198 | -18.3 | Business and interviews. Confident British presenter. |
| `bf_lily` | 187 | 187 | -21.2 | **Moderator.** Calm, even, authoritative. |
| `bm_daniel` | 122 | 194 | -21.0 | Current affairs. Newsreader delivery. |
| `bm_fable` | 115 | 184 | -23.8 | Fiction and kids. Brightest voice in the set. |
| `bm_george` | 139 | 167 | -21.1 | **Long-form narrator.** History; unhurried and warm. |
| `bm_lewis` | 85 | 176 | -23.6 | Late-night, noir. Deepest and gravelly. |

## Picking for a job

| You want | Reach for | Why |
|---|---|---|
| A default two-host pair | `af_heart` + `am_michael` | The shipped `two-host` cast; warm, proven |
| A moderator | `bf_lily`, `af_aoede`, `bm_george` | Mid pitch, near-median pace, even level |
| An advocate / lead | `am_adam`, `am_fenrir`, `bf_isabella` | Loud and clear, median-or-faster |
| A skeptic / analyst | `af_kore`, `af_alloy`, `am_echo` | Lower pitch, unhurried, dry |
| Authority or documentary | `am_onyx`, `bm_lewis` | 85–87 Hz, dark timbre |
| A long-form solo narrator | `bm_george`, `af_bella`, `am_echo` | Unhurried, even, easy over 20+ minutes |
| **A sleep story or meditation** | **`af_nicole`** | **120 wpm, soft and intimate — the outlier, and perfect here** |
| Brisk news-style delivery | `bf_emma`, `af_river`, `bm_daniel` | The fast end, 194–208 wpm |
| A character or novelty | `am_santa`, `bm_fable` | Distinctive rather than neutral |

## By podcast type

What to reach for when the request names a kind of show rather than a role.

| Podcast type | Cast + voices |
|---|---|
| Debate / panel | `panel` — `bf_lily` host, `am_adam` advocate, `af_kore` skeptic |
| Interview prep, company diligence | `two-host` with `af_aoede` + `am_adam` — clear and businesslike |
| History, long documentary | `solo` with `bm_george`; `am_onyx` when it wants gravitas |
| Daily news brief | `solo` with `bm_daniel` or `bf_emma` — fast, no dwelling |
| Sleep, meditation, wind-down | `solo` with `af_nicole`, and nothing else |
| True crime, investigation | `solo` with `am_onyx` or `bm_lewis` |
| Kids, fiction, storytelling | `two-host` with `bm_fable` + `af_bella` |
| Product or tool evaluation | `panel` when the choice is contested, else `two-host` |

## Rotation

Each cast slot lists three interchangeable voices. The renderer picks the **least
recently used** one per episode, so a weekly series varies without ever being random —
random would re-pick on every re-render and blow the per-line TTS cache, which is keyed
on the voice.

- The pick is pinned in the episode's `.tts-cache/cast.lock.json`, so re-rendering after
  a script fix keeps the same voices and the same warm cache.
- History lives in the state dir (`voice-rotation.json`), eight deep per slot.
- `--no-rotate` freezes every slot to its first (default) voice.
- A blocked voice leaves every pool: `config.py set voice_blocklist=af_nova,am_santa`, or
  `--exclude-voices` for one render. Blocking every voice in a slot is an error naming the
  slot, not a silent fallback to a voice the listener rejected.

**Adding to a pool:** put the safest choice first — it is the default and the
`--no-rotate` pick — and keep every voice in a pool interchangeable for that role. A pool
is not a place to park a voice you would not want to hear in that seat.

## What to avoid

- **`af_nova` for anything long.** 5.7 dB below the median level; normalisation lifts its noise with it.
- **Two same-accent, same-gender voices in one episode.** The most common mistake. A listener tracks a
  conversation by voice, and two American men 10 Hz apart is one voice with a memory problem.
- **`af_nicole` in a conversation.** It is a beautiful voice reading the wrong material — 35% slower than
  everything around it, so it reads as hesitant rather than calm when someone answers it.
- **Fixing a temperament with `@ speed`.** Pushing a 208 wpm voice to 0.85 to make it "thoughtful" sounds
  processed. Pick a voice whose own pace is close, then nudge by a few percent.

## The other 26

Not English, and unused by the shipped casts, but available for a bilingual episode or a quoted passage:

- **Spanish** `ef_dora` `em_alex` `em_santa` · **French** `ff_siwis` · **Italian** `if_sara` `im_nicola`
- **Portuguese** `pf_dora` `pm_alex` `pm_santa` · **Hindi** `hf_alpha` `hf_beta` `hm_omega` `hm_psi`
- **Japanese** `jf_alpha` `jf_gongitsune` `jf_nezumi` `jf_tebukuro` `jm_kumo`
- **Mandarin** `zf_xiaobei` `zf_xiaoni` `zf_xiaoxiao` `zf_xiaoyi` `zm_yunjian` `zm_yunxi` `zm_yunxia` `zm_yunyang`

A voice only speaks its own language well. Putting English through `jf_alpha` produces an accent, not a
translation.
