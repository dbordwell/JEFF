# AJZ — your framework running on real numbers

Hi Jeff — the dashboard is built and pulling live data. Before we finish it, there's one
decision only you can make, and it's about the investing side rather than the computer
side.

---

## First: it works

Your AJZ Rule 3.0 is running exactly as you wrote it:

```
AJZ Score       = (2 × Revenue Growth) + Gross Margin + FCF Margin + (0.5 × ROIC)
AJZ Value Score = AJZ Score ÷ Forward P/E
Conviction      = your five 1–5 scores
```

Nothing about the method changed. It pulls from Financial Modeling Prep every morning,
and the file on your desktop is simply up to date when you open it. No button to press.

---

## The thing we need you to look at

Here are ten stocks from your original list — the AJZ Value Scores in your Copilot chat
next to what the live data produces today:

| Stock | Score in your chat | Live today |
|-------|-------------------:|-----------:|
| NVDA  | 16.9 | **11.6** |
| LLY   |  9.0 |  **5.7** |
| TSM   |  8.0 |  **6.3** |
| AVGO  |  7.5 |  **5.3** |
| ANET  |  7.0 |  **3.9** |
| BE    |  8.0 |  **1.4** |
| MELI  |  6.5 |  **3.3** |
| HOOD  |  6.0 |  **4.7** |
| AMZN  |  3.5 |  **3.6** |
| PLTR  |  3.0 |  **2.3** |

Almost everything comes in lower — mostly around two-thirds of what you saw.

### Why they're different

We can't be certain, but the most likely explanation is simple: **Copilot had no access
to market data.** It couldn't fetch a real revenue growth figure or a real forward P/E.
Those example scores were almost certainly illustrations — realistic-looking numbers
invented to show you what the output *would* look like.

There's a tell. The stocks where the two columns agree are the slow-growers (AMZN 3.5 vs
3.6). The ones that diverge most are the high-growth names, where an invented growth rate
would be furthest off. Revenue growth is doubled in your formula, so a wrong growth number
moves the score more than anything else.

**This is not a problem with your framework.** The formula is fine. It's that the numbers
you set your cut-offs against were never real ones — and now, for the first time, you have
real ones.

---

## What it does to your buckets

Your thresholds are: **AJZ Value 7+** is high, **below 5** is a warning, **below 3** is an
exit. Against live data, out of 24 stocks:

- **Only 3 clear 7** (NVDA 11.6, CRM 9.4, META 9.2). So "Core Holding" has become a very
  high bar.
- **"Aggressive Position" is now almost impossible to reach.** It needs AJZ Value 7+ *and*
  conviction of 16–20. But you score your quality names 21+, so anything that clears 7 goes
  straight to Core Holding instead. In your chat, BE, HOOD and MELI sat here — today none
  of them do.
- **About half the list triggers a WARNING**, because most solid businesses land below 5.

That last one is the one we'd flag hardest. An alert that fires on half your portfolio
every week stops being information — you'd learn to scroll past it, and then it won't be
there when something genuinely goes wrong.

---

## Three ways to go

**Option A — change nothing.** Perfectly reasonable. It just means Core Holding is rare,
most good businesses read as Defensive Compounders, and warnings are common enough that
you'll mostly ignore them.

**Option B — rescale the cut-offs to real data.** Keep your framework identical and move
the thresholds so the *proportions* land where you originally intended — roughly the top
handful as Core, a middle group as solid, and warnings genuinely rare. Something like
7 → 5, 5 → 3.5, 3 → 2 would put today's list back in the shape your chat table showed.

**Option C — make it relative.** Instead of fixed numbers, define the bands by rank: the
top ~20% of your list is "high AJZ", the bottom ~20% is weak. This self-calibrates and
never needs revisiting when the market moves. The trade-off is that a score stops having a
fixed meaning — a 6 might be "high" one year and "middling" another.

Our suggestion is **B**, because it keeps your numbers meaning what you intended while
matching reality. But this is your call — it's your methodology and your risk tolerance,
and we'd rather ask than quietly pick for you.

---

## The questions

1. **Which option** — A, B, or C? If B, do the suggested cut-offs feel right, or would you
   set them somewhere else?
2. **Conviction range.** You've scored almost everything 21+. Is that deliberate (these are
   all genuinely high-conviction names) or would you use more of the 1–5 range if you
   revisited them? It affects whether "Aggressive Position" is a bucket worth keeping.
3. **What should a WARNING mean to you?** Something to glance at, or something that should
   be rare enough to make you stop and look? That tells us where to put the line.
4. **Your list.** We've started with 24 names from your chats. Which do you actually want
   tracked? Around 40–50 is comfortable — the limit isn't the computer, it's that you have
   to hand-score conviction for each one.

---

## One housekeeping item

Your FMP API key is sitting in plain text inside the old workbook, and that file has been
emailed around. Worth logging into FMP and regenerating it. The new dashboard keeps the key
in a separate settings file on your PC, so the spreadsheet itself is safe to share with
anyone.
