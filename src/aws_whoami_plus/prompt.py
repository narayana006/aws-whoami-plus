"""Shell prompt snippets.

The snippets read only environment variables, so they add no delay and make no
AWS calls each time the prompt is drawn. They show "[aws:<profile>@<region>]"
and turn red when the profile name matches a glob (default "*prod*", override
with AWS_WHOAMI_PROMPT_PROD).
"""

BASH = r'''# aws-whoami-plus prompt segment for bash.
# Add to ~/.bashrc:  eval "$(aws-whoami-plus --prompt bash)"
__aws_whoami_segment() {
  local p="${AWS_PROFILE:-${AWS_DEFAULT_PROFILE:-}}"
  local r="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
  if [ -z "$p" ]; then
    [ -n "${AWS_ACCESS_KEY_ID:-}" ] || return 0
    p="env-keys"
  fi
  local pattern="${AWS_WHOAMI_PROMPT_PROD:-*prod*}"
  local color=36
  case "$p" in
    $pattern) color=31 ;;
  esac
  # \001 and \002 mark the colour codes as zero-width for readline.
  printf '\001\033[%sm\002[aws:%s%s]\001\033[0m\002 ' "$color" "$p" "${r:+@$r}"
}
case "$PS1" in
  *__aws_whoami_segment*) ;;
  *) PS1='$(__aws_whoami_segment)'"$PS1" ;;
esac
'''

ZSH = r'''# aws-whoami-plus prompt segment for zsh.
# Add to ~/.zshrc:  eval "$(aws-whoami-plus --prompt zsh)"
__aws_whoami_segment() {
  local p="${AWS_PROFILE:-${AWS_DEFAULT_PROFILE:-}}"
  local r="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
  if [[ -z "$p" ]]; then
    [[ -n "${AWS_ACCESS_KEY_ID:-}" ]] || return 0
    p="env-keys"
  fi
  local pattern="${AWS_WHOAMI_PROMPT_PROD:-*prod*}"
  local color=cyan
  [[ "$p" == ${~pattern} ]] && color=red
  local text="[aws:$p${r:+@$r}]"
  # Double any % so profile names cannot inject prompt escapes.
  print -rn -- "%F{$color}${text//\%/%%}%f "
}
setopt PROMPT_SUBST
if [[ "$PROMPT" != *__aws_whoami_segment* ]]; then
  PROMPT='$(__aws_whoami_segment)'"$PROMPT"
fi
'''

SNIPPETS = {"bash": BASH, "zsh": ZSH}
