# AJZ v2.1 — the colour problems, fixed

Hi Jeff — both things you flagged about the colours are sorted, and the fix for the
second one turned into something better than putting your formatting back.

**Short version:**

1. **The Forward P/E colours were backwards.** A real bug, and worth knowing about
   because the colour was telling you the opposite of what the number said.
2. **Your colour-coding didn't save.** Our fault, not yours — and now the colours you
   pick don't just stick, they drive the whole workbook.

Everything from v2.0 below that, unchanged, in case you want it again.

**To update:** download the new **AJZ-Setup.exe** and double-click it. That is the whole
thing. It doesn't matter which folder you run it from, you don't need the config file
again, and there's nothing to uninstall first. Your watchlist and any settings you have
changed carry across.

After that, click **AJZ Dashboard** on your desktop as usual.

## 1. Forward P/E was shaded the wrong way round

This one was a genuine bug and you found it without knowing you had.

The shading is meant to run strongest-colour-for-best down to no-colour-for-worst. That
works for AJZ Score and AJZ Value, where a bigger number is better. Forward P/E runs the
other way — cheap is the good end — and we had it painting the *expensive* end as though
it were the best.

So CRWD at 176x and NET at 240x were sitting in the strongest blue on the sheet, and
"Cheap" had no colour at all. If you'd been reading down that column by colour, it was
pointing you at exactly the wrong stocks. Now "Cheap" is the strong end and "Bubble" is
the pale one.

## 2. Your colour-coding, and what it now does

You coloured the category names in column A of Settings to make the tables easier to
read, saved, and the refresh wiped them.

That was our fault. The workbook gets rebuilt from scratch every refresh — that's what
stops it drifting into a half-updated state, and it's why the old file's `#REF!` errors
can't happen here. But it means anything we don't deliberately save off your sheet gets
destroyed. We'd already learned that with your category tables and fixed it for the words
and the numbers. We never thought about the formatting.

Rather than just put your colours back, we made them the point:

> **Fill a category's name cell with a colour, and that category takes that colour
> everywhere it appears** — the Top Rankings columns and the Opportunity Matrix headers,
> not just the Settings sheet.

Your three tables are now the legend for the whole workbook. A few notes:

- **Any colour in Excel's picker works**, including the theme colours along the top row.
- **The text colour looks after itself.** Pick something dark and the writing turns white.
- **Leave a cell alone and nothing changes** — it keeps our shading, which still runs
  best-to-worst and re-spaces itself when you add or remove a category.
- **To go back to ours,** clear the fill: Home → Fill Colour → No Fill.

This also answers the other half of what you said. The three category columns all came
out in much the same blue, which makes them blur together when you read across. Give AJZ
Score, Forward P/E and AJZ Value their own colour families and they separate immediately.
That's now yours to set rather than ours to guess.

---

# Everything below is from v2.0

Unchanged — repeated here so you have it all in one place.

## What changed

**Conviction is gone**, along with everything that depended on it: the sheet, the two
columns on Top Rankings, the old Opportunity Matrix buckets, and the conviction half of
each alert. Your five scores weren't thrown away — the first refresh after this update
saves them to *AJZ Dashboard - conviction scores (archived).xlsx* in the AJZ folder, in
case you ever want them back.

**Your three tables are now the categories**, everywhere. Top Rankings reads across:

| AJZ Score | Score Category | Forward P/E | P/E Category | AJZ Value | Value Category |
|---:|---|---:|---|---:|---|
| 280.1 | Legendary | 24.7 | Premium | 11.3 | Generational |
| 157.6 | Legendary | 18.3 | Fair Value | 8.6 | Elite |
| 116.8 | Elite | 16.9 | Fair Value | 6.9 | Exceptional |

**Opportunity Matrix** is now your Primary Screen — one column per AJZ Value category.

**Movers works.** You were right that it wasn't updating. It was worse than that: it was
never finished, so it would never have updated no matter how long you waited. It now
flags anything where the AJZ Score moved more than 25%, the forward P/E moved more than
10%, or the stock changed category — and when nothing has moved, it says so in as many
words, rather than looking broken.

**Dashboard** is empty and waiting for whatever you want there later. The status line at
the top stays: it's the only thing that tells you whether the numbers are today's.

## You can change the categories yourself

This is the part worth five minutes. On the **Settings** sheet, each of your three tables
is a list of categories. Each row is a name and the number it starts at.

```
Category name         Starts at    Range (automatic)    Stocks now
Legendary                   150    150 and above            13
Exceptional                 120    149.9 – 120               7
Elite                       100    119.9 – 100               3
```

- **Change a number** and the `Range` column redraws immediately, before you refresh.
- **Rename a category** — type over the name. Nothing else needs to know.
- **Add one** — type into a blank row at the bottom of that table. It sorts into place by
  its number at the next refresh; you don't have to put it in the right position.
- **Remove one** — clear both its cells.
- **Start over** — clear the whole table and the original comes back.

You never have to keep the ranges lined up. You only ever set where a category *starts*,
so there's no way to leave a gap that a stock could fall through.

## We widened the list to 50

Your 24 are all still there. We added 26 more — bigger names across more sectors, so the
screen isn't almost entirely software. **These are candidates, not suggestions.** A screen
isn't a portfolio: a ticker being here means "rank this", not "buy this". Delete any you
don't want, or set Active to NO on the **Universe** sheet, and add your own.

Two of the new ones came straight in at the top — ADBE at 14.1 and INTU at 11.9, both
above NVDA. That is the screen doing its job on names that simply weren't in front of you
before.

## Your Value table is working

Across 50 names, every one of your seven categories has stocks in it:

```
Generational   4     Excellent   8     Expensive   9
Elite          6     Attractive  6
Exceptional   10     Fair        7
```

That's a well-built table. Your Forward P/E table fills all eight categories too.

## One thing to look at

Your AJZ Score table still leans top-heavy: **19 of 50 land in "Legendary"**, and
`Weak to Dead` is empty. It's much better on the wider list than it was on 24 — going
broader pulled real names into `Good` and `Fair to Poor`, which were empty before — but
nearly two in five stocks sharing the top category means the word isn't separating much.

We built it exactly as you wrote it. Those are your numbers and it isn't our call. It's
worth a look because it's the same thing you spotted yourself between version 2.0 and 2.1
of your own change list: your AJZ Value table used to top out at "5.0 and above", you saw
it was swallowing everything, and you split it into Generational / Elite / Exceptional.
That's the table that now spreads perfectly.

The reason the Score table behaves this way: it's built from margins and growth, and
almost any large, profitable company clears 150. PLTR scores 257 and is one of the worst
values on your sheet. So the distinctions you care about are probably higher up. But you
know what you meant by those words better than we do — and the `Stocks now` column on
Settings shows you the count beside each one, live, so you can move them and watch what
happens.

One other thing you may notice: COST comes out "Fair to Poor" on AJZ Score. That isn't a
bug — a retailer runs thin gross margins by nature, and your formula weights margins
heavily. Worth knowing the screen will always treat that kind of business harshly.
