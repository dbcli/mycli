function _mycli_dsn_aliases --argument-names insert_prefix incomplete
    env MYCLI_LLM_OFF=1 mycli --list-dsn 2>/dev/null | while read -l alias
        if test -n "$alias"; and test (string sub -s 1 -l (string length -- "$incomplete") -- "$alias") = "$incomplete"
            printf '%s%s\n' "$insert_prefix" "$alias"
        end
    end
end

# Spelling out the args here is much faster than invoking mycli with _MYCLI_COMPLETE.
function _mycli_is_positional_db_arg
    set -l words (commandline -opc)
    set -l current (commandline -ct)
    set -l positional_count 0
    set -l options_ended 0
    set -l expects_value 0

    for word in $words[2..-1]
        if test $expects_value -eq 1
            set expects_value 0
            continue
        end
        if test $options_ended -eq 1
            set positional_count (math $positional_count + 1)
            continue
        end

        switch "$word"
            case --
                set options_ended 1
            case '--*=*'
            case --host --hostname --port --user --username --socket --pass --password --password-file --vault-address --vault-mount --vault-secret --vault-password-field --vault-username-field --ssl-mode --ssl-ca --ssl-capath --ssl-cert --ssl-key --ssl-cipher --tls-version --database --dsn --completions --prompt --toolbar --logfile --checkpoint --myclirc --local-infile --login-path --execute --init-command --charset --character-set --batch --format --throttle --use-keyring --keepalive-ticks --ssh-jump --ssh-options
                set expects_value 1
            case '-*'
                set -l option_length (string length -- "$word")
                if test $option_length -eq 1
                    set positional_count (math $positional_count + 1)
                    continue
                end
                for short_index in (seq 2 $option_length)
                    set -l short_option (string sub -s $short_index -l 1 -- "$word")
                    if contains -- "$short_option" h P u S p g e R l D d
                        if test $short_index -eq $option_length
                            set expects_value 1
                        end
                        break
                    end
                end
            case '*'
                set positional_count (math $positional_count + 1)
        end
    end

    test $expects_value -eq 0; and test $positional_count -eq 0; and not string match -q -- '-*' "$current"
end

function _mycli_complete_paths --argument-names insert_prefix incomplete
    __fish_complete_path "$incomplete" | while read -l candidate
        printf '%s%s\n' "$insert_prefix" "$candidate"
    end
end

function _mycli_click_completions
    set -l response (env MYCLI_LLM_OFF=1 _MYCLI_COMPLETE=fish_complete COMP_WORDS=(commandline -cp) COMP_CWORD=(commandline -ct) mycli)

    for completion in $response
        set -l metadata (string split -m 1 ',' -- "$completion")
        switch "$metadata[1]"
            case dir
                __fish_complete_directories "$metadata[2]"
            case file
                __fish_complete_path "$metadata[2]"
            case plain
                echo "$metadata[2]"
        end
    end
end

function _mycli_completion
    command -q mycli; or return 1

    set -l current (commandline -ct)
    set -l words (commandline -opc)
    set -l previous ''
    if test (count $words) -gt 1
        set previous "$words[-1]"
    end

    switch "$current"
        case '--dsn=*'
            _mycli_dsn_aliases '--dsn=' (string replace -- '--dsn=' '' "$current")
            return
        case '-d*'
            _mycli_dsn_aliases '-d' (string sub -s 3 -- "$current")
            return
        case '--database=*'
            _mycli_dsn_aliases '--database=' (string replace -- '--database=' '' "$current")
            return
        case '-D*'
            _mycli_dsn_aliases '-D' (string sub -s 3 -- "$current")
            return
        case '--socket=*'
            _mycli_complete_paths '--socket=' (string replace -- '--socket=' '' "$current")
            return
        case '-S*'
            _mycli_complete_paths '-S' (string sub -s 3 -- "$current")
            return
        case '--checkpoint=*'
            _mycli_complete_paths '--checkpoint=' (string replace -- '--checkpoint=' '' "$current")
            return
        case '--batch=*'
            _mycli_complete_paths '--batch=' (string replace -- '--batch=' '' "$current")
            return
    end

    _mycli_click_completions

    switch "$previous"
        case -d --dsn -D --database
            _mycli_dsn_aliases '' "$current"
        case -S --socket --checkpoint --batch
            _mycli_complete_paths '' "$current"
        case '*'
            if _mycli_is_positional_db_arg
                _mycli_dsn_aliases '' "$current"
            end
    end
end

# erase supplied completions which only work for --dsn
complete --erase --command mycli

complete --no-files --keep-order --command mycli --arguments '(_mycli_completion)'
