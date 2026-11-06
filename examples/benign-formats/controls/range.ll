; Inclusive signed integer range predicate. Equal bounds include that value;
; reversed bounds cannot satisfy both comparisons.
define i1 @in_range(i32 %value, i32 %lower, i32 %upper) {
entry:
  %lo = icmp sge i32 %value, %lower
  %hi = icmp sle i32 %value, %upper
  %result = and i1 %lo, %hi
  ret i1 %result
}
