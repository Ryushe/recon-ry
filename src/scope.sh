#!/usr/bin/env bash
# Input/promotion containment shared by foreground and background runners.

scope_enabled() {
    [[ -n "${RECON_RY_SCOPE_FILE:-}${RECON_RY_EXACT_HOST:-}" ]]
}

scope_check() {
    python3 "$SCRIPT_DIR/scripts/scope_filter.py" "$@"
}

# Crawler arguments for katana/exact_katana. `-fs fqdn` is unconditional: an
# input hostname is never relaxed to its registrable domain, scope or not.
# The `-cs` crawl regex needs an explicit scope, so an unscoped run stays
# fqdn-bounded and follows redirects as it did before the scope gates existed.
katana_crawl_args() {
    local tool="$1" input_file="$2"
    case "$tool" in
        katana|exact_katana) ;;
        *) return 0 ;;
    esac
    local args="-fs fqdn"
    if scope_enabled; then
        local crawl_scope
        crawl_scope=$(scope_check crawl-regex --input "$input_file") || return 2
        printf -v crawl_scope "%q" "$crawl_scope"
        args="$args -cs $crawl_scope -dr"
    fi
    printf '%s' "$args"
}

scope_filter_artifacts() {
    scope_enabled || return 0
    local project_dir="$1" directory file candidate evidence
    for directory in "$project_dir" "$project_dir/.tmp_run" "${CURRENT_HISTORY_DIR:-}"; do
        [[ -d "$directory" ]] || continue
        for file in wild.txt hosts.txt urls.txt alive.txt params_raw.txt params.txt jsfiles.txt url_seed.txt; do
            [[ -f "$directory/$file" ]] || continue
            candidate=$(mktemp "$directory/.scoped.XXXXXX") || return 1
            if ! scope_check filter --input "$directory/$file" --output "$candidate"; then
                rm -f "$candidate"
                return 1
            fi
            if ! cmp -s "$directory/$file" "$candidate"; then
                # Retain rejected/resumed evidence, never treat it as active input.
                mkdir -p "$project_dir/.scope-evidence" || return 1
                evidence=$(mktemp "$project_dir/.scope-evidence/$file.XXXXXX") || return 1
                cp "$directory/$file" "$evidence" || return 1
                mv "$candidate" "$directory/$file" || return 1
            else
                rm -f "$candidate"
            fi
        done
    done
}

scope_prepare_input() {
    local tool="$1" source="$2"
    # Archive/local operations do not grant authorization to their outputs.
    case "$tool" in
        subfinder|crt_sh|assetfinder|amass|waybackurls|gau|waymore|passive_param_recon|gau_params|uro|js_files|unclutter_jsfiles|url_ranking|dork_scan)
            if scope_enabled; then
                scope_check validate || return 2
            fi
            printf '%s' "$source"
            return 0
            ;;
        *)
            if ! scope_enabled; then
                # Containment is opt-in. Without --scope-file the tool runs
                # against its unfiltered input, as it did before the scope
                # gates existed; warn so the run log records the exposure.
                log_warning "Tool $tool running unfiltered: no --scope-file supplied"
                printf '%s' "$source"
                return 0
            fi
            ;;
    esac
    scope_check validate || return 2
    if [[ -z "$source" ]]; then
        printf ''
        return 0
    fi
    local directory="${PROJECT_DIR:-$(dirname "$source")}/.scope-inputs"
    local filtered
    mkdir -p "$directory" || return 1
    filtered=$(mktemp "$directory/input.XXXXXX") || return 1
    scope_check filter --input "$source" --output "$filtered" || return 2
    if [[ ! -s "$filtered" ]]; then
        log_error "Tool $tool blocked: no authorized input (DNS answers do not authorize IP scanning)"
        return 2
    fi
    printf '%s' "$filtered"
}
