# Run Notes: `autoresearch/mar10`

Derived artifact. Treat this file as a narrative summary, not the source of truth.

## Current State

- Baseline commit: `814dc55`
- Baseline `val_bpb`: `1.447119`
- Current best commit: `5b486fb`
- Current best `val_bpb`: `1.386688`
- Current branch HEAD: `5b486fb`

## Canonical Precedence

- `results.tsv`
- control state JSON
- control report Markdown
- narrative Markdown

## Frontier Settings

- `TOTAL_BATCH_SIZE` = `32768`
- `DEVICE_BATCH_SIZE` = `16`
- `EMBEDDING_LR` = `0.6`
- `UNEMBEDDING_LR` = `0.00475`
- `MATRIX_LR` = `0.046`
- `SCALAR_LR` = `0.5`
- `WEIGHT_DECAY` = `0.2`
- `ADAM_BETAS` = `(0.8, 0.95)`
- `WARMUP_RATIO` = `0.0`
- `WARMDOWN_RATIO` = `0.5`
- `FINAL_LR_FRAC` = `0.05`
- `DEPTH` = `4`

## Confirmed Additive Wins

- `814dc55` `1.447119` baseline
- `fbb1d57` `1.402182` reduce total batch size to 32768
- `71804ff` `1.395468` raise matrix lr to 0.045
- `9837e67` `1.393572` set final lr frac to 0.05
- `f19ef7f` `1.387882` raise matrix lr to 0.046
- `5b486fb` `1.386688` raise unembedding lr to 0.00475

## Dead Ends

- `72a5f2b` `1.965557` increase depth to 6
- `c3d864d` `1.404766` shorten warmdown ratio to 0.3
- `1a693c2` `1.403206` lower matrix lr to 0.035
- `012019d` `1.398821` lower weight decay to 0.1
- `c22c546` `1.401598` lower embedding lr to 0.5
- `08d1dcd` `1.422114` add warmup ratio of 0.02
- `33557c2` `1.396161` raise matrix lr to 0.05
- `d4405c1` `1.412259` lower unembedding lr to 0.003
- `14dfec5` `1.404114` raise unembedding lr to 0.005
- `b11e958` `1.404287` change adam betas to (0.85, 0.95)
- `4068fa1` `1.395652` set final lr frac to 0.1
- `30a4507` `1.401963` lower weight decay to 0.15
- `f967f3c` `1.405763` change adam betas to (0.825, 0.95)
- `1d0f677` `1.395900` lower final lr frac to 0.025
- `3716980` `1.394921` raise final lr frac to 0.075
- `6a9099a` `1.396012` lower weight decay to 0.175
- `7868df1` `1.399596` lower final lr frac to 0.04
- `d057589` `1.394738` raise final lr frac to 0.06
- `68eba62` `1.402610` shorten warmdown ratio to 0.45
- `e80fda7` `1.399982` lengthen warmdown ratio to 0.55
- `ba30ea6` `1.394027` reduce device batch size to 8
- `90f1966` `1.427855` add warmup ratio of 0.005
- `8842fba` `1.394424` lower matrix lr to 0.044
- `9fab8f4` `1.393558` raise matrix lr to 0.047
- `4d17416` `1.392811` lower matrix lr to 0.043
- `551b586` `1.393546` raise matrix lr to 0.048
- `3ebc6cf` `1.398442` lower matrix lr to 0.042
- `3e4400d` `1.398853` raise unembedding lr to 0.00425
- `02a89ab` `1.395257` raise unembedding lr to 0.0045
- `ee2a4cc` `1.391437` lower unembedding lr to 0.00375
- `e6f685b` `1.390232` lower unembedding lr to 0.004625
- `7f5e16e` `1.392895` raise unembedding lr to 0.004875
- `b16925d` `1.402170` lower unembedding lr to 0.0035
- `e634d49` `1.389167` raise weight decay to 0.21
- `d4abce5` `1.388756` lower weight decay to 0.19
- `fc7c5e8` `1.386732` raise weight decay to 0.22
- `cff3339` `1.388004` lower weight decay to 0.18
- `ffe5a60` `1.392434` raise scalar lr to 0.525
- `38f26e5` `1.393486` raise scalar lr to 0.55
- `6dbcf54` `1.388378` lower scalar lr to 0.475

## Latest Evaluated Band

- `fc7c5e8` `1.386732` `discard` raise weight decay to 0.22
- `cff3339` `1.388004` `discard` lower weight decay to 0.18
- `6dbcf54` `1.388378` `discard` lower scalar lr to 0.475
- `d4abce5` `1.388756` `discard` lower weight decay to 0.19
- `e634d49` `1.389167` `discard` raise weight decay to 0.21

## Non-Informative Outcomes

- `13` `timeout after 600 seconds`

## Next Candidate

- `adam_betas_08_096` change adam betas to (0.8, 0.96)
