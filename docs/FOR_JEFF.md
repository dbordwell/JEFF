# AJZ v2.0 — your changes, built

Hi Jeff — everything on your "Requested Changes for Items 2.1" list is in.

**To update:** download the new **AJZ-Setup.exe** and double-click it. That is the whole
thing. It doesn't matter which folder you run it from, you don't need the config file
again, and there's nothing to uninstall first. Your watchlist and any settings you have
changed carry across.

After that, click **AJZ Dashboard** on your desktop as usual.

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

## Your colours now stick

You coloured the category names in column A to make the tables easier to read, and the
refresh wiped them. That was our fault — the workbook gets rebuilt from scratch every
time, and we were only saving the words and the numbers off that sheet, not the
formatting.

It saves the colour now, and it does more than put it back:

**Fill a category's name cell with a colour and that category takes that colour
everywhere it appears** — the Top Rankings columns and the Opportunity Matrix headers,
not just the Settings sheet. The category tables are the legend for the whole workbook.

- Any colour in Excel's picker works, including the theme colours across the top row.
- The text colour looks after itself. Pick something dark and the writing turns white.
- Leave a cell alone and it keeps the shading we chose, which still runs dark-to-light
  best-to-worst and re-spaces itself when you add or remove a category.
- To go back to ours, clear the fill (Home → Fill Colour → No Fill).

This also answers the other thing you flagged — the three category columns all coming out
in the same blue. Give AJZ Score, Forward P/E and AJZ Value their own colour families and
they stop blurring together. That's yours to set now rather than ours.

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
