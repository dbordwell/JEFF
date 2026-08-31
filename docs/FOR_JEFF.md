# AJZ v3.0 — pre-profit companies, and your colours

Hi Jeff — three things.

**To update:** download the new **AJZ-Setup.exe** and double-click it. No config file,
nothing to uninstall, doesn't matter what folder you run it from. Your watchlist,
settings and history all carry across.

## 1. Pre-profit companies now have their own bucket

You were right that they shouldn't just be listed and forgotten, and right again that
defaulting the P/E to zero would blow the sheet up. Here's what they do now.

**Top Rankings** has a second section under the main ranking:

```
  18   ADBE   ...                     (ranked on AJZ Value)
  19   TFC    ...
─────────────────────────────────────────────────────────────
  Pre-Profit — ranked on AJZ Score only
  (no forward P/E, and never included in any average)
  P1   RIVN   132.4   —   —
  P2   ...
```

They're numbered **P1, P2, P3** rather than continuing 20, 21, 22 — because the number
above is an AJZ Value Score and the number here is an AJZ Score, and those are different
quantities. Numbering them in one sequence would invite reading them as one list.

**Opportunity Matrix** gets a column on the far right for them, headed with the AJZ Score
rather than a Value Score. It's deliberately grey rather than coloured: it isn't a rung
on the Value ladder, it's the companies the ladder can't measure.

**They never touch an average**, exactly as you asked. The Portfolio Quality Index and
every other headline number ignores them completely.

**Why AJZ Score is the right ranking for them:** it's revenue growth, gross margin, FCF
margin and ROIC. None of those needs the company to be profitable. So it says something
true about a pre-profit business, where AJZ Value Score — which is Score ÷ P/E — can't
say anything at all.

**You can rename the bucket.** There's a new row on **Settings**: *"Name for companies
with no forward P/E"*. Type whatever you want there — "Pre-Profit", "Early Stage",
"Unprofitable" — and it changes on both sheets.

**One more thing worth knowing.** The Notes column now tells you *why* a stock has no
P/E, and there are two different answers:

- *"not expected to be profitable next year"* — a fact about the company. This is the
  normal case and it's the one you want to track.
- *"no analyst estimates for this symbol"* — a fact about the **data**, not the company.
  If you see this, **check the ticker is right.** A symbol that doesn't exist looks
  exactly like this, and so does a symbol that quietly matches a different company.

That last point is worth a look for SpaceX in particular — it's privately held, so there
is no real ticker for it. Whatever symbol is in your Universe sheet for it is either
returning nothing or returning somebody else's numbers.

## 2. Your colours — the actual reason they never stuck

I owe you an apology on this one. You reported it twice, and both times you were right.

The Settings sheet is protected so you can't accidentally overwrite the parts we
regenerate. What I missed is that Excel's sheet protection **also blocks changing a
cell's fill colour** — even on the cells we'd deliberately left unlocked for you to
edit. So when you tried to colour the category names, Excel was refusing the change.
Nothing you did was wrong; the door was locked.

That's fixed. You can now colour the category name cells on Settings, and — as of the
last update — **whatever colour you pick becomes that category's colour everywhere it
appears**: the Top Rankings columns and the Opportunity Matrix headers, not just the
Settings sheet. Your three tables are the legend for the whole workbook.

- Any colour in Excel's picker works, including the theme colours along the top row.
- The text colour looks after itself — pick something dark and the writing turns white.
- To go back to ours: Home → Fill Colour → No Fill.

This is also the fix for the three category columns all coming out the same blue. Give
AJZ Score, Forward P/E and AJZ Value their own colour families and they stop blurring
together when you read across.

## 3. Excel going "not responding" — still looking

I pulled apart the generated file to check whether it's the workbook's fault. It isn't:
47 cell styles, no volatile formulas, largest sheet is 19 rows by 12 columns. There's
nothing in that file for Excel to struggle with.

So it's something about how it's being opened rather than what's in it. My leading
theory is that after a refresh we ask Windows to open the workbook, and if Excel is
already busy — or already has that file open, or is sitting mid-edit in another workbook
— that request can stall and freeze the whole application behind a dialog you may not
be able to see.

**To confirm it, I need the log file:**

```
%LOCALAPPDATA%\AJZ\logs\refresh.log
```

Paste that path into the Windows Explorer address bar and email me the file. Two
questions that would help as much as the log:

1. **How many tickers are you up to now?** There's no caching of the fundamentals yet —
   it's 8 separate API calls per stock, one after another — so a much bigger universe
   makes each refresh take much longer. That's a known thing we deferred at 24 tickers
   and it may simply have come due.
2. **Does Excel still hang if you open the dashboard file directly** instead of using
   the desktop shortcut? That single answer separates my main theory from everything
   else.

## 4. Truist and Adobe

Noted, and it's the good kind of noticing — the rebucketing is doing exactly what it
should. Whether they're genuinely generational is your call and not the spreadsheet's;
what matters is that the sheet moved them because the underlying numbers moved, and you
can see it happen. If the cut-offs feel wrong now that real names are landing in the top
band, that's what the Settings table is for.

---

# From v2.1

## Forward P/E was shaded the wrong way round

This one was a genuine bug and you found it without knowing you had.

The shading is meant to run strongest-colour-for-best down to no-colour-for-worst. That
works for AJZ Score and AJZ Value, where a bigger number is better. Forward P/E runs the
other way — cheap is the good end — and we had it painting the *expensive* end as though
it were the best.

So CRWD at 176x and NET at 240x were sitting in the strongest blue on the sheet, and
"Cheap" had no colour at all. If you'd been reading down that column by colour, it was
pointing you at exactly the wrong stocks. Now "Cheap" is the strong end and "Bubble" is
the pale one.

## Your colour-coding, and what it now does

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
