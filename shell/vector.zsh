# vector-companion: `vector` shortcut + Vector announces long terminal commands.
# Thresholds/on-off live in the Vector app (Notifications). This only pre-filters very short commands.
_vector_root="${${(%):-%x}:A:h:h}"
alias vector="$_vector_root/.venv/bin/vector"
zmodload zsh/datetime
: ${VECTOR_MIN_SECONDS:=5}
# never announce these (interactive/long-lived programs)
typeset -ga VECTOR_IGNORE=(vim nvim vi nano emacs less more man top htop btop ssh claude tmux screen watch tail fg vector open code cursor)
# ignore these only when run with no arguments (REPLs)
typeset -ga VECTOR_REPLS=(python python3 ipython node bash zsh sh conda irb)

_vector_preexec() { _vector_cmd="$1"; _vector_start=$EPOCHREALTIME }
_vector_precmd() {
  local rc=$?
  [[ -z "$_vector_start" ]] && return
  local el=$(( EPOCHREALTIME - _vector_start )) cmd="$_vector_cmd"
  unset _vector_start _vector_cmd
  (( el < VECTOR_MIN_SECONDS )) && return
  [[ -d "$_vector_root/logs" ]] || mkdir -p "$_vector_root/logs"
  (( rc == 130 )) && return            # you pressed Ctrl-C yourself
  local -a words=(${(z)cmd})
  local first=${words[1]:t}
  while [[ $first == *=* || $first == sudo || $first == time || $first == caffeinate || $first == nohup ]]; do
    words=(${words[2,-1]}); first=${words[1]:t}; [[ -z $first ]] && return
  done
  (( ${VECTOR_IGNORE[(Ie)$first]} )) && return
  (( ${#words} == 1 && ${VECTOR_REPLS[(Ie)$first]} )) && return
  print -r -- "$(date '+%F %T')  zsh: $first rc=$rc ${el%.*}s -> hook" >> "$_vector_root/logs/zsh.log" 2>/dev/null
  ( "$_vector_root/.venv/bin/vector" hook terminal --rc $rc --seconds $el --cmd "$first" --cwd "$PWD" >/dev/null 2>&1 & )
}
autoload -Uz add-zsh-hook
add-zsh-hook preexec _vector_preexec
# run first so we see the real exit code before other prompt hooks (conda etc.)
precmd_functions=(_vector_precmd ${precmd_functions:#_vector_precmd})
