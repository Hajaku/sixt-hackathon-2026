---
tags: [forecast, demand, findings, project-4]
date: 2026-11-13
status: findings done, forecast code to do
code: fleetopt/forecast.py (to do)
notebook: notebooks/02_demand_distribution.ipynb
---

# Demand

Findings on the demand process: pickups, rental lengths, dispersion, and the demand to come $D_{s,k,d}$ in the horizon.
Back to [[Overview]] · [[Project Plan]] (§2) · [[Base Revenue]] · [[Decisions]]

**In one line:** pickups are Poisson given one Gamma factor per station × category × calendar week (±13 %). Lengths are one pooled truncated geometric, independent of everything. The weekday pattern depends on the station type. There is no trend, and no correlation between cells.

## Data and notation
- **History:** `completed` + `open` rentals, i.e. every pickup in the 8 weeks before day 1 (Mon 2027-01-04 to Sun 2027-02-28). Day 1 (2027-03-01) is a Monday, so the horizon is exactly two calendar weeks.
- **Rule for bookings** (see [[Decisions]]): future bookings never enter the history-based estimates ($\lambda$, lengths, $v$, base). They may be used to *condition* the forecast on what is known at day 1, as committed car-days and for the week-1 update below.
- **Notation:**
  - $P_{s,k,t}$: pickups on date $t$;
  - $T_{s,k,t}$: cars on rent on $t$ (from rentals picked up at $s$);
  - $\lambda_{s,k,\mathrm{wd}}$: mean pickups per weekday;
  - $\pi, S$: pmf and survival of the rental length $L$ (car-days, both ends counted);
  - $D_{s,k,d}$: demand to come, i.e. cars on rent on horizon day $d$ from rentals booked on or after day 1.
- **Truncation:** $T$ is complete only from the 10th day of the window on (max length 10). Pickups are complete everywhere.

## 1. Weekday pattern
The station type sets the weekday pattern:
- **Downtown** peaks Fri–Sun: Saturday pickups ≈ 2.2× the mean, Saturday cars on rent ≈ 1.45×; Mon–Thu are low.
- **Airports** peak on Monday and Thursday and are low at the weekend.
- Within a type, the stations' weekday indices almost coincide in every category. So $\lambda_{s,k,\mathrm{wd}} \approx \text{level}_{s,k}\times\text{profile}_{\text{type},\mathrm{wd}}$ is a candidate with far fewer parameters than 280 means of 8 values each.

![[demand_weekday_profile.png]]

Cars on rent per weekday, per station × category (boxes over the 6–7 fully observed weeks; dots = days; black tick = mean):

![[demand_on_rent_by_weekday.png]]

## 2. Rental length
- **One distribution for everything:** a geometric truncated at 10 days, $\pi(l)\propto q^{l-1}$, with $q = 0.694$ (airport) and $0.699$ (downtown). The mean is ≈ 3.0 car-days in every group.
- **χ² homogeneity tests** (lengths 8–10 merged):

  | H0: same length pmf for … | p |
  |---|---:|
  | the 8 station type × category groups | 0.54 |
  | categories (pooled) | 0.72 |
  | airport vs. downtown | 0.37 |
  | stations within a type × category | 0.02 |
  | all 40 cells | 0.04 |

  The station effects are weak (224–273 df) and too small to matter. So we pool, at most by station type.
- **Independent of everything we can check:**
  - pickup weekday and history week;
  - how busy the pickup day was (ρ = 0.00);
  - the other rentals of the same day: no day-level clustering, Var(z) = 1.02;
  - lead time: Spearman ≈ 0.

![[demand_length_pmf.png]]
![[demand_length_independence.png]]

**Why this matters.** Assume pickups on day $p$ are Poisson($\lambda_p$), independent across days, and each rental draws its length independently from $\pi_p$. Then by thinning and superposition
$$T_d \sim \mathrm{Poisson}\Big(\sum_p \lambda_p\, S_p(d-p+1)\Big)$$
for **any** length distribution. The pmf sets only the mean of $T$ and its autocorrelation over days. What the result needs is the independence, which holds. **Mean check:** the convolution $\hat\lambda * \hat S$ reproduces the observed mean cars on rent to within 0.5 % on average (sd 7 % per cell).

**Lead time** (for the committed vs. to-come split):
- Airports book later. Share booked ≤ 7 days ahead: airport ≈ 0.84, downtown ≈ 0.78.
- Share booked on the pickup day: airport ≈ 0.20, downtown ≈ 0.17.
- Lead and length are independent (see [[Decisions]], 2026-11-13).

## 3. Dispersion: not Poisson
- **Test:** the pooled statistics of Var/mean per (station, category, weekday) were compared with **200 simulated histories** under Poisson pickups and independent lengths. The simulations use the same window, truncation and sample sizes.
- **Result:** both series are far outside the null (p < 1/200).

| | observed | null 5–95 % |
|---|---:|---:|
| pickups: pooled excess $\phi=\sum\mathrm{Var}/\sum\mu-1$ | 0.34 | −0.07 … 0.08 |
| pickups: median Var/mean | 1.02 | 0.86 … 0.97 |
| cars on rent: pooled excess $\phi$ | 0.61 | −0.12 … 0.11 |
| cars on rent: median Var/mean | 1.18 | 0.79 … 0.98 |

![[demand_dispersion_null.png]]

## 4. The weekly shock
**What it is.** Each station × category has its own demand level for each calendar week, Mon–Sun. Some weeks the cell is busier than its average on every day, other weeks quieter.

**Evidence:**
1. **Persistence:** the excess variance of weekly totals is 5.8× that of single days. It would be 1 for independent daily shocks and 7 for one shock shared by all 7 days. The ratio is 4.9–7.8 in every category.
2. **Calendar-aligned:** daily residuals correlate within the week (lag 1: +0.07 to +0.32 depending on the weekday pair), but **not from Sunday to Monday (−0.01)**. The autocorrelation is gone by lag 5.
3. **No carry-over:** a cell's weekly level has correlation −0.12 / −0.21 / −0.16 with the next 1 / 2 / 3 weeks, about the −1/7 that centering alone produces. To predict week 8, the 7-week mean (MSE 287) beats the last two weeks (358) and the last week (602).
4. **Not shared:** weekly levels correlate −0.01 between stations of the same type × category and +0.05 between categories at the same station. Daily pickup correlations are ≈ 0, and the network variance ratio is 1.03.

![[demand_weekly_shock.png]]

**Model:**
$$P_{s,k,d}\mid G \sim \mathrm{Poisson}\big(G_{s,k,w(d)}\,\lambda_{s,k,\mathrm{wd}(d)}\big),\qquad G_{s,k,w}\overset{\text{iid}}{\sim}\Gamma\big(\text{shape } 1/v,\ \text{rate } 1/v\big),$$
with lengths i.i.d. from $\pi$. Given $G$, $T$ and $D$ are Poisson. Marginally, a week's pickups are NegBin.

**Estimation.** Given $\lambda$, the weekly total $W_{s,k,w}$ is sufficient for $G_{s,k,w}$: the split of $W$ over the days is multinomial and free of $G$. So $W\sim\mathrm{NegBin}(\Lambda_{s,k},\,1/v)$, giving 40 cells × 8 weeks = 320 values.
- **Method of moments:** $\hat v = \sum(s_W^2-\bar W)/\sum\bar W^2 = \mathbf{0.017}$ (bootstrap SE 0.003). That is a ±13 % weekly level.
- **NegBin ML** with $\hat\Lambda=\bar W$ gives 0.014. It is biased down because $\Lambda$ is estimated from the same 8 values, so we use the method-of-moments value.
- **By group:**

  | Group | $\hat v$ | SE |
  |---|---:|---:|
  | airport | 0.021 | 0.008 |
  | downtown | 0.016 | 0.004 |
  | economy | 0.024 | 0.006 |
  | compact | 0.010 | 0.004 |
  | midsize | 0.019 | 0.005 |
  | premium | 0.010 | 0.006 |

  None of these differences is significant after multiple testing, so we use **one pooled $v$**.
- Gamma vs. log-normal can't be told apart at this CV and sample size, and it doesn't matter.

**No trend.** The apparent decline of downtown economy (−2.6 %/week fitted) comes from a few high early weeks at single stations. Those are these shocks, not a trend.

## 5. Demand to come (pseudo-snapshots, route B)
**Method:** treat every Monday $t_0$ of the history as a pseudo "day 1". For $d = 1..14$, count the cars on rent on $t_0+d-1$ from rentals booked on or after $t_0$. Monday anchors match the real horizon in both the booking offset and the weekday. There are 8 snapshots for $d\le7$ and 7 for $d\ge8$.
- **Shape:** a ramp over the first ~5 days (near days are mostly booked already), then the weekday pattern.
- **Committed vs. to come:** the residual correlation of $D$ with the pseudo-committed $B$ is **+0.17** (slope +0.14) for days 1–7. The weekly shock explains this: a busy week shows up both in what is already booked and in what is still to come.

![[demand_to_come_snapshots.png]]
![[demand_committed_vs_to_come.png]]

## Implications for the forecast and the model
- **Point forecast:**
  $$E[D_{s,k,d}] = \sum_{p=1}^{d}\lambda_{s,k,\mathrm{wd}(p)}\;P(L\ge d-p+1,\ \ell\le p-1)$$
  (route A in [[Project Plan]]), with plain 8-week weekday means for $\lambda$. Don't weight recent weeks. Optionally use level × type profile.
- **Week-1 update from the bookings** (Gamma–Poisson conjugacy). Let $n_B$ be the number of week-1 pickups already booked before day 1, and $\mu_B$ its expectation under the model above. Then
  $$E[G_{s,k,1}\mid n_B] = \frac{1/v + n_B}{1/v + \mu_B},\qquad 1/v \approx 59.$$
  For example, 40 booked where 30 were expected gives $E[G]\approx1.11$, i.e. +11 % demand to come in week 1. Week 2 stays at 1, since the shocks don't carry over.
  - [ ] Validate on the pseudo-snapshots: does the update predict $D$ better than the unconditional mean?
- **Only the marginals enter the objective.** The plan is fixed before the horizon, so expected profit is separable over cell-days: $\sum_{s,k,d}E[\mathrm{rev}_{s,k,d}(D_{s,k,d}, a_{s,k,d})]$. Only the marginal of each $D_{s,k,d}$ enters, and upgrades couple only independent categories on the same station and day. So the correlation across days is irrelevant for the expected profit.
- **But the marginal is wider than Poisson:** $\mathrm{Var}[D]=\mu(1+v\mu)$, which is ×1.9 at $\mu=50$. That flattens the concave expected-revenue curves $E[\mathrm{rev}](a)$, so the last cars at busy stations are worth less than a Poisson model says.
- **Scenario generator** (expected-revenue curves, SAA, our own scorer): per cell draw $G_{s,k,1}, G_{s,k,2}$, then Poisson pickups per day and geometric lengths. Rentals from week 1 that are still on rent in week 2 keep their week-1 factor. Condition $G_{s,k,1}$ on the bookings as above.
- **Score spread:** the shocks also widen the spread of the 30-scenario mean profit, which matters for the "within 2 SE is a tie" rule.
