---
tags: [model, project-4]
model: M0
level: L1
based_on:
status: reference
code: fleetkit/baseline.py (baseline_plan)
---

# M0 Baseline

The organizers' baseline from `fleetkit.baseline_plan`. A rule, not an optimization model. It's the reference our models must beat.
Back to [[Models]] · [[Experiments]]

## Idea
For each station $s$ and category $k$:
$$\text{need}_{s,k} = \frac{\text{pickups per day}_{s,k} \cdot \overline{\text{rental length}}_k}{u_s}, \qquad \text{add}_{s,k} = \max(0,\ \text{need}_{s,k} - f^0_{s,k})$$
All of it is added on **day 1**, rounded to whole cars and scaled down per category to the cap $\bar A_k$.

## What it ignores
- Committed car-days, one-way flows and the day-by-day fleet
- Removals and transfers
- Price factors and fare buckets (it serves 100 % of demand at the base price)
- Upgrades between categories
- Holding cost vs. marginal revenue

## Properties
- Only adds cars, so it's always valid.
- On the starter data it adds 96 cars over 21 rows.

## Experiments
See [[Experiments]] rows with model `[[M0 Baseline]]`.
