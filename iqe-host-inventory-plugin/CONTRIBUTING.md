# High level overview of contribution process

1. Create a new branch in GitLab (in the actual repo, not a fork)
2. Push changes to said branch
3. When ready, create an MR
4. Have the MR reviewed
5. "Merge" the MR.

Note:
This repo is set up with `--ff-only`, so if you encounter issues with conflicts,
make sure you update your local branch before you push changes.

# FAQ

## What if I can't merge?

This is an intended side effect of `--ff-only` and consistent with the rebase
approach to maintaining branches. To merge your branch, your branch
needs to include all commits from master, followed by your commits. If your
branch is missing any of the commits from master, you will be unable to merge.

## How do I fix it?

You can fix this problem by bringing your branch up-to-date with master via a
rebase operation. Generally, this should be as simple as:

```git pull origin master --rebase```

If your branch has become outdated, you may need to resolve some conflicts.
After doing so you will be able to merge.
