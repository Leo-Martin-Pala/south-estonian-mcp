# Experimental Seto and Mulgi copula agreement

The checker uses each variety's existing descriptive GiellaLT analyser. It
warns when a sentence begins with an unambiguous first- or second-person
singular nominative personal pronoun followed immediately by a present
indicative copula with only incompatible readings. The response code is
`copula-agreement` and the span uses Divvun's UTF-16 offsets.

| Variety | Attested forms and source |
| --- | --- |
| Mulgi | EKI's [Mulgi sõnaraamat, oleme](https://arhiiv.eki.ee/dict/mulgi/index.cgi?Q=olema) lists `oleme <olla, ole, (ta) om ~ oo ~ o>`. The Autumn 2013 issue of [Üitsainus Mulgimaa](https://www.mulgimaa.ee/userfiles/%C3%9Ctsainud-mulgimaa/Sygis-2013.pdf) includes `KAS SIA OLET MIIS?` and `mia ole`. The analyser uses the internal lemma `olema`. |
| Seto | Hagu and Pajusalu, [Seto keele teejuht, pp. 26–27](https://www.umakultuur.ee/_uploads/materjal/seto_keele_teejuht.pdf#page=26), give `ma olõ tulnu`, `tä om kotoh`, and `nimä’ omma’ kotoh`. The Setomaa newspaper unit `setomaa_newspaper_corpus_cc:seto-01-2012-vahtsot:s15` attests `sa olõt`. |

The rule infers a potential agreement issue from the analyses and suggests one
attested form for the corresponding person. Unknown forms, competing readings
and regional variants can reduce coverage. For example, the current Seto
analyser has a competing verb reading for `ma`, and the Mulgi analyser has
competing readings for `sia`. Some recognised first-person copula forms also
have connegative and imperative readings, so the rule abstains on those when
checking a second-person subject. Other patterns and natural-text false-alarm
rates remain unevaluated.

The test sentences are constructed controls for routing, agreement and spans.
They serve as regression tests. The Modal deployment uses the existing
analysers under `/data/giella-share`.
