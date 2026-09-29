# BUG-04: coupon applied twice

A checkout with a $25 subtotal and `DOUBLE5` should return $20. The original handler returned $15 because it assigned a 1,000-cent discount to a five-dollar coupon.

The fix uses the same 500-cent discount for `SAVE5` and `DOUBLE5`, retaining the existing zero floor. Six parameterized regression cases exercise the two coupons with subtotals of 2,500, 500, and 200 cents. The original Phase 1 scenario also now passes and no longer declares BUG-04 as an expected defect.

Verification includes replaying the regression suite against a temporary copy with the old discount behavior restored. The $25/DOUBLE5 case must fail against that version and pass against the fixed implementation. This is a focused mutation check, not a general mutation-testing framework.

The CI validator also tests a different failure mode: an expected defect passing while a healthy test fails. Total failure counts remain unchanged, but the per-test gate rejects the swap.

Limits: this is an in-memory testbed with deliberate defects, not a production checkout service. Known failing test identities are checked; a different error inside an already expected-failing test can still require human review.
