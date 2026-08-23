# AJZ — your framework running on real numbers

Hi Jeff — the dashboard is built and pulling live data. Before we finish it, there's one
decision only you can make, and it's about the investing side rather than the computer.

## It works

Your AJZ Rule 3.0 runs exactly as you wrote it:

```
AJZ Score       = (2 × Revenue Growth) + Gross Margin + FCF Margin + (0.5 × ROIC)
AJZ Value Score = AJZ Score ÷ Forward P/E
Conviction      = your five 1–5 scores
```

Nothing about the method changed. Click **AJZ Dashboard** on your desktop and it fetches
the latest figures and opens the updated file — one click, a few seconds.

## The numbers are lower than you've seen

Ten of your names, as scored in your Copilot chat versus live data today:

| Stock | In your chat | Live today |
|-------|-------------:|-----------:|
| NVDA  | 16.9 | **11.8** |
| LLY   |  9.0 |  **5.8** |
| TSM   |  8.0 |  **6.2** |
| AVGO  |  7.5 |  **5.2** |
| ANET  |  7.0 |  **3.9** |
| BE    |  8.0 |  **1.5** |
| MELI  |  6.5 |  **3.3** |
| HOOD  |  6.0 |  **4.2** |
| AMZN  |  3.5 |  **4.0** |
| PLTR  |  3.0 |  **2.3** |

**Your framework isn't the problem.** Copilot had no access to market data — it couldn't
fetch a real revenue growth figure or a real forward P/E, so those scores were almost
certainly illustrations: realistic-looking numbers to show you the shape of the output.

The tell is that the slow-growers match (AMZN 3.5 vs 4.0) while the high-growth names
diverge most — exactly what you'd expect if growth rates were invented, since your formula
doubles that input.

So for the first time you're looking at real numbers. That's the good news. It just means
the cut-offs need a second look.

## What that does to your buckets

Your thresholds are **7+ high**, **below 5 warning**, **below 3 exit**. Against live data,
across 24 stocks:

- **Only 3 clear 7** (NVDA, CRM, META). "Core Holding" has become a very high bar.
- **"Aggressive Position" is now unreachable.** It needs 7+ *and* conviction 16–20, but you
  score your quality names 21+, so anything clearing 7 goes to Core Holding instead.
- **About half the list triggers a WARNING**, because most solid businesses land below 5.

That last one is what we'd flag hardest. An alert firing on half your portfolio stops being
information — you'd learn to scroll past it, and then it won't be there when something
genuinely goes wrong.

## Three ways to go

**A — change nothing.** Reasonable. Core Holding stays rare, most good businesses read as
Defensive Compounders, warnings are common enough that you'll mostly ignore them.

**B — rescale the cut-offs.** Keep the framework identical, move the thresholds so the
*proportions* land where you originally intended. Something like **7 → 5, 5 → 3.5, 3 → 2**
puts today's list back in the shape your chat table showed.

**C — make it relative.** Define bands by rank: top ~20% is "high", bottom ~20% is weak.
Self-calibrating, but a score stops having a fixed meaning year to year.

**We'd suggest B** — it keeps your numbers meaning what you intended while matching
reality. But it's your methodology and your risk tolerance, so we'd rather ask.

## The questions

1. **Which option — A, B, or C?** If B, do those cut-offs feel right?
2. **Conviction range.** You've scored almost everything 21+. Deliberate, or would you use
   more of the 1–5 range if you revisited? It decides whether "Aggressive Position" is a
   bucket worth keeping.
3. **What should a WARNING mean to you?** Something to glance at, or rare enough to make
   you stop and look? That tells us where to put the line.
4. **Your list.** We've started with the 24 names from your chats. Which do you actually
   want tracked? Around 40–50 is comfortable — the limit isn't the computer, it's that you
   hand-score conviction for each one.

> **One thing you'll notice:** 19 of the 24 show "Needs Conviction". Only the five you
> scored with Copilot are filled in. We didn't invent the rest — conviction is the one
> input that's genuinely your judgement, and making it up would corrupt the whole thing.
