; Clamp value to inclusive signed bounds. Reversed bounds preserve value.
define i32 @clamp(i32 %value, i32 %lower, i32 %upper) {
entry:
  %reversed = icmp sgt i32 %lower, %upper
  %below = icmp slt i32 %value, %lower
  %above = icmp sgt i32 %value, %upper
  %bounded_hi = select i1 %above, i32 %upper, i32 %value
  %bounded = select i1 %below, i32 %lower, i32 %bounded_hi
  %result = select i1 %reversed, i32 %value, i32 %bounded
  ret i32 %result
}
