Architectural ownership:
For code and technical plans, trace the execution path and identify the owner of
each changed behaviour or shared fact, including dependencies, forks, and tools
outside the diff. Check that the fix lives with that owner and uses established
project mechanisms. Boundary translation belongs to the adapter that owns that
boundary. Flag compensation for another component's defect, duplicated
responsibility, and hidden coupling. Judge simplicity across the whole system:
a smaller diff or an extracted helper does not repair misplaced ownership.
For each finding, cite the path, name the proper owner, and give the smallest
fix there. For a necessary workaround, state the blocker, maintenance cost, and
whether explicit approval is evidenced. Report ownership findings or state that
none were found; if ownership cannot be verified, name the missing evidence.
