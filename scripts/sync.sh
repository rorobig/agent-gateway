#!/usr/bin/env bash
# After a git push: make Argo CD pick it up now instead of within 30 s.
for app in $(kubectl -n argocd get applications -o name); do
  kubectl -n argocd annotate "$app" argocd.argoproj.io/refresh=normal --overwrite >/dev/null
done
echo "Argo CD refreshing. The proxy applies new policies within a few seconds."
