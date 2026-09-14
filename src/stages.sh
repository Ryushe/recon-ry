#!/usr/bin/env bash

# Stage execution module

# Shared interruption flag (best-effort; may be overridden by parent shell)
: "${INTERRUPTED:=false}"
: "${EYE_DATE_STAMP:=}"
: "${CURRENT_HISTORY_DIR:=}"

dir_has_contents() {
    local dir_path="$1"
    [[ -d "$dir_path" ]] && find "$dir_path" -mindepth 1 -print -quit 2>/dev/null | grep -q .
}

expand_eyewitness_store_template() {
    local template="$1"
    local project_dir="$2"
    local domain="$3"
    local url="$4"
    local large_project_dir="$5"
    local project_basename

    project_basename="$(basename "$project_dir")"
    large_project_dir="${large_project_dir/#\~/$HOME}"

    template="${template//\{\{PROJECT_DIR\}\}/$project_dir}"
    template="${template//\{\{PROJECT_BASENAME\}\}/$project_basename}"
    template="${template//\{\{LARGE_PROJECT_DIR\}\}/$large_project_dir}"
    template="${template//\{\{RECON_DIR\}\}/$SCRIPT_DIR}"
    template="${template//\{\{DOMAIN\}\}/$domain}"
    template="${template//\{\{URL\}\}/$url}"
    template="${template/#\~/$HOME}"

    printf '%s\n' "$template"
}

resolve_eyewitness_store_dir() {
    local project_dir="$1"
    local domain="${2:-}"
    local url="${3:-}"
    local store_template
    local large_project_dir

    store_template="$(get_tool_info "eyewitness" "store_dir")"
    large_project_dir="$(get_tool_info "eyewitness" "large_project_dir")"

    if [[ -n "$large_project_dir" && ( -z "$store_template" || "$store_template" == "{{PROJECT_DIR}}/eyewitness" ) ]]; then
        store_template="{{LARGE_PROJECT_DIR}}/{{PROJECT_BASENAME}}/web/recon/eyewitness"
    elif [[ -z "$store_template" ]]; then
        store_template="{{PROJECT_DIR}}/eyewitness"
    fi

    expand_eyewitness_store_template "$store_template" "$project_dir" "$domain" "$url" "$large_project_dir"
}

# Ensure eyewitness stage runs last when present
reorder_stages_eyewitness_last() {
    local stages="$1"
    local reordered=()
    local saw_eyewitness=false
    local stage

    for stage in $stages; do
        if [[ "$stage" == "eyewitness" ]]; then
            saw_eyewitness=true
            continue
        fi
        reordered+=("$stage")
    done

    if [[ "$saw_eyewitness" == "true" ]]; then
        reordered+=("eyewitness")
    fi

    printf '%s\n' "${reordered[*]}"
}

filter_exact_host_artifacts() {
    local project_dir="$1"
    local target_url="$2"
    local temp_dir="$project_dir/.tmp_run"

    python3 - "$target_url" \
        "$project_dir/urls.txt" "$temp_dir/urls.txt" \
        "$project_dir/alive.txt" "$project_dir/params.txt" \
        "$project_dir/params_raw.txt" "$project_dir/jsfiles.txt" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import sys

target = urlparse(sys.argv[1] if "://" in sys.argv[1] else f"https://{sys.argv[1]}").hostname
if not target:
    raise SystemExit("exact-urls requires a URL with a hostname")
target = target.lower()
for raw_path in sys.argv[2:]:
    path = Path(raw_path)
    if not path.is_file():
        continue
    kept = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        value = raw.strip()
        if not value:
            continue
        parsed = urlparse(value if "://" in value else f"//{value}")
        if parsed.hostname and parsed.hostname.lower() == target:
            kept.append(raw)
    path.write_text("\n".join(dict.fromkeys(kept)) + ("\n" if kept else ""), encoding="utf-8")
PY
}

# Check if stage dependencies are met
check_stage_dependencies() {
    local stage="$1"
    local project_dir="$2"

    local depends_on=$(get_stage_info "$stage" "depends_on")

    if [[ -z "$depends_on" || "$depends_on" == "[]" ]]; then
        return 0
    fi

    # Check if dependency stages have been completed
    # (We can check if their output files exist)
    for dep_stage in $depends_on; do
        local dep_tools=$(get_stage_info "$dep_stage" "tools")
        local has_output=false

        for tool in $dep_tools; do
            local outputs=$(get_tool_info "$tool" "outputs")
            for output in $outputs; do
                if [[ -s "$project_dir/$output" ]]; then
                    has_output=true
                    break 2
                fi
            done
        done

        if [[ "$has_output" == "false" ]]; then
            log_debug "Dependency stage $dep_stage not completed"
            return 1
        fi
    done

    return 0
}

# Execute a stage
execute_stage() {
    local stage="$1"
    local project_dir="$2"
    local domain="$3"
    local url="$4"
    local temp_dir="$project_dir/.tmp_run"

    scope_filter_artifacts "$project_dir" || return 2
    log_info "Running stage: $stage"

    # Check if stage is enabled
    if ! is_stage_enabled "$stage"; then
        log_warning "Stage $stage is disabled, skipping"
        return 0
    fi

    # Special check for subdomain_enum: tools need a domain; infer from wild.txt if URL not provided
    if [[ "$stage" == "subdomain_enum" ]]; then
        if [[ -z "$domain" ]]; then
            if [[ -s "$project_dir/wild.txt" ]]; then
                domain=$(head -n 1 "$project_dir/wild.txt" | sed -e 's|^https\?://||' -e 's|/.*||')
                if [[ -n "$domain" ]]; then
                    log_info "Subdomain enum domain inferred from wild.txt: $domain"
                else
                    log_warning "Stage subdomain_enum skipped: unable to infer domain from wild.txt"
                    return 0
                fi
            else
                log_warning "Stage subdomain_enum skipped: no URL provided and wild.txt not found"
                log_info "Subdomain enumeration requires --url to be specified"
                return 0
            fi
        fi
    fi

    # Passive archive profiles can run from a URL/domain seed without requiring
    # a prior live stage or a pre-existing wild.txt.
    if [[ "$stage" == "passive_url_discovery" || "$stage" == "passive_param_discovery" ]]; then
        if [[ ! -s "$project_dir/wild.txt" && ! -s "$temp_dir/wild.txt" && -n "$domain" ]]; then
            mkdir -p "$temp_dir"
            printf '%s\n' "$domain" > "$temp_dir/wild.txt"
            log_info "Passive seed domain: $domain"
        fi
    fi

    # Check dependencies
    if ! check_stage_dependencies "$stage" "$project_dir"; then
        log_warning "Stage $stage dependencies not met, skipping"
        return 0
    fi

    # Get stage configuration
    local parallel=$(get_stage_info "$stage" "parallel")
    local tools=$(get_stage_info "$stage" "tools")

    if [[ -z "$tools" ]]; then
        log_warning "No tools configured for stage $stage"
        return 0
    fi

    # Prepare tool execution parameters
    local tool_params=()
    local skipped_tools=0

    for tool in $tools; do
        # Check if tool is enabled
        if ! is_tool_enabled "$tool"; then
            log_debug "Tool $tool is disabled, skipping"
            skipped_tools=$((skipped_tools + 1))
            continue
        fi

        # Check if required files exist
        if ! check_required_files "$tool" "$project_dir"; then
            log_debug "Tool $tool missing required files, skipping"
            skipped_tools=$((skipped_tools + 1))
            continue
        fi

        # Get tool outputs
        local outputs=$(get_tool_info "$tool" "outputs")
        local primary_output=$(echo "$outputs" | awk '{print $1}')
        local output_file="$project_dir/$primary_output"
        if [[ "$primary_output" == "wild.txt" || "$primary_output" == "urls.txt" ]]; then
            output_file="$temp_dir/$primary_output"
        fi
        if [[ "$stage" == "passive_url_discovery" || "$stage" == "exact_url_discovery" ]] && [[ "$primary_output" == "urls.txt" ]]; then
            output_file="$project_dir/$primary_output"
        fi

        # Get tool inputs
        local required_files=$(get_tool_info "$tool" "required_files")
        local input_file=""
        if [[ -n "$required_files" && "$required_files" != "[]" ]]; then
            local req_file
            req_file="$(echo "$required_files" | awk '{print $1}')"
            if [[ "${PROFILE:-}" == "full" && "$stage" == "secret_scan" && "$req_file" == "jsfiles.txt" && -n "${CURRENT_HISTORY_DIR:-}" && -f "$CURRENT_HISTORY_DIR/$req_file" && -s "$CURRENT_HISTORY_DIR/$req_file" ]]; then
                # Full recon reruns should use this run's JS delta when available.
                # Standalone `secrets` intentionally scans the project root backlog.
                input_file="$CURRENT_HISTORY_DIR/$req_file"
            elif [[ -f "$temp_dir/$req_file" && -s "$temp_dir/$req_file" ]]; then
                input_file="$temp_dir/$req_file"
            else
                input_file="$project_dir/$req_file"
            fi
        fi

        # Build tool parameter string
        if [[ "$tool" == "eyewitness" ]]; then
            if [[ -z "${EYE_DATE_STAMP:-}" ]]; then
                EYE_DATE_STAMP="$(date +"%-m-%-d-%Y")"
            fi
            local eye_store
            local eye_root
            eye_store="$(resolve_eyewitness_store_dir "$project_dir" "$domain" "$url")"
            eye_root="$eye_store"
            local eye_history_run_dir="$eye_root/history/$EYE_DATE_STAMP"
            local eye_had_existing_content=false
            if dir_has_contents "$eye_root"; then
                eye_had_existing_content=true
            fi
            mkdir -p "$eye_history_run_dir"

            if [[ -n "${EYE_INPUT:-}" ]]; then
                if [[ -f "$EYE_INPUT" ]]; then
                    input_file="$EYE_INPUT"
                else
                    input_file="$temp_dir/eyewitness_input.txt"
                    printf '%s\n' "$EYE_INPUT" > "$input_file"
                fi
                output_file="$eye_store"
                tool_params+=("$tool:$input_file:$output_file:$domain:$url")
                continue
            fi

            local params_input=""
            local alive_input=""
            local use_history_inputs=false

            # For full profile reruns with existing EyeWitness content, only scan
            # this run's history delta files instead of full project files.
            if [[ "${PROFILE:-}" == "full" && -n "${CURRENT_HISTORY_DIR:-}" ]]; then
                if [[ "$eye_had_existing_content" == "true" ]]; then
                    use_history_inputs=true
                fi
            fi

            if [[ "$use_history_inputs" == "true" ]]; then
                if [[ -f "$CURRENT_HISTORY_DIR/params.txt" && -s "$CURRENT_HISTORY_DIR/params.txt" ]]; then
                    params_input="$CURRENT_HISTORY_DIR/params.txt"
                fi

                if [[ -f "$CURRENT_HISTORY_DIR/alive.txt" && -s "$CURRENT_HISTORY_DIR/alive.txt" ]]; then
                    alive_input="$CURRENT_HISTORY_DIR/alive.txt"
                fi
            fi

            if [[ "$use_history_inputs" == "false" ]]; then
                if [[ -f "$temp_dir/params.txt" && -s "$temp_dir/params.txt" ]]; then
                    params_input="$temp_dir/params.txt"
                elif [[ -f "$project_dir/params.txt" && -s "$project_dir/params.txt" ]]; then
                    params_input="$project_dir/params.txt"
                fi

                if [[ -f "$temp_dir/alive.txt" && -s "$temp_dir/alive.txt" ]]; then
                    alive_input="$temp_dir/alive.txt"
                elif [[ -f "$project_dir/alive.txt" && -s "$project_dir/alive.txt" ]]; then
                    alive_input="$project_dir/alive.txt"
                fi
            fi

            if [[ -n "$params_input" ]]; then
                tool_params+=("$tool:$params_input:$eye_store:$domain:$url")
            fi

            if [[ -n "$alive_input" ]]; then
                tool_params+=("$tool:$alive_input:$eye_store:$domain:$url")
            fi

            if [[ -z "$params_input" && -z "$alive_input" ]]; then
                log_debug "Tool $tool missing alive.txt and params.txt, skipping"
                ((skipped_tools++))
            fi
            continue
        fi

        tool_params+=("$tool:$input_file:$output_file:$domain:$url")
    done

    # Check if any tools are runnable
    if [[ ${#tool_params[@]} -eq 0 ]]; then
        log_warning "No runnable tools for stage $stage (all skipped: $skipped_tools)"
        return 0
    fi

    local exit_code=0
    # Capture failures explicitly even under errexit.
    if [[ "$parallel" == "true" ]]; then
        log_verbose "Running ${#tool_params[@]} tools in parallel"
        run_tools_parallel "${tool_params[@]}" || exit_code=$?
    else
        log_verbose "Running ${#tool_params[@]} tools sequentially"
        run_tools_sequential "${tool_params[@]}" || exit_code=$?
    fi

    if [[ $exit_code -eq 130 || "${INTERRUPTED:-false}" == "true" ]]; then
        INTERRUPTED=true
        log_warning "Stage $stage interrupted"
        return 130
    elif [[ $exit_code -eq 124 ]]; then
        log_warning "Stage $stage incomplete: tool timeout; partial evidence retained"
    elif [[ $exit_code -gt 0 ]]; then
        log_warning "Stage $stage incomplete: one or more tools failed"
    else
        log_success "Stage $stage completed successfully"
    fi

    scope_filter_artifacts "$project_dir" || return 2
    return $exit_code
}

# Run reconnaissance for project
run_recon_project() {
    local project_dir="$1"
    local url="$2"
    local profile="$3"

    local RECON_RY_EXACT_HOST="${RECON_RY_EXACT_HOST:-}"
    if [[ "$profile" == "exact-host" || "$profile" == "exact-urls" || "$profile" == "exact-urls-header" ]]; then
        [[ -n "$url" ]] || { log_error "Exact profile requires --url"; return 2; }
        RECON_RY_EXACT_HOST="$url"
    fi
    export RECON_RY_EXACT_HOST
    if scope_enabled; then
        scope_check validate || return 2
        scope_filter_artifacts "$project_dir" || return 2
    fi

    log_info "Starting recon with profile: $profile"
    log_info "Project directory: $project_dir"
    if auth_seed_is_enabled; then
        write_auth_metadata "$project_dir"
        log_info "Auth seed enabled for supported HTTP tools; metadata written to $project_dir/.auth/auth_metadata.json"
    fi

    # Check if project directory has existing data
    local has_urls=false
    local has_wild=false

    if [[ -s "$project_dir/urls.txt" ]]; then
        has_urls=true
        log_info "Found existing urls.txt"
    fi

    if [[ -s "$project_dir/wild.txt" ]]; then
        has_wild=true
        log_info "Found existing wild.txt"
    fi

    # If no existing data and no URL provided, exit
    if [[ "$has_urls" == "false" && "$has_wild" == "false" && -z "$url" ]]; then
        log_error "No existing data found and no URL provided"
        log_error "Please provide --url or ensure urls.txt/wild.txt exists in project directory"
        exit 1
    fi

    # Determine domain from URL
    local domain=""
    if [[ -n "$url" ]]; then
        # Extract domain from URL
        domain=$(echo "$url" | sed -e 's|^https\?://||' -e 's|/.*||')
        log_info "Target: $domain"
    fi

    # Get stages for profile
    local stages=$(get_profile_stages "$profile")
    stages=$(reorder_stages_eyewitness_last "$stages")

    if [[ -z "$stages" ]]; then
        log_error "Profile $profile not found or has no stages"
        exit 1
    fi

    log_info "Stages to run: $stages"

    local temp_dir="$project_dir/.tmp_run"
    rm -rf "$temp_dir"
    mkdir -p "$temp_dir"

    if [[ -n "$url" ]]; then
        printf '%s\n' "$url" > "$temp_dir/url_seed.txt"
    fi
    if [[ "$profile" == "exact-urls" || "$profile" == "exact-urls-header" ]]; then
        # Reuse URL-discovery tools with a transient single-host input. This is
        # not a wildcard inventory and is never promoted into project wild.txt.
        printf '%s\n' "$domain" > "$temp_dir/wild.txt"
    fi

    if [[ "$DIR_ONLY" == "true" ]]; then
        stages="dir_enum"
    fi

    local dir_enum_in_profile=false
    for stage in $stages; do
        if [[ "$stage" == "dir_enum" ]]; then
            dir_enum_in_profile=true
            break
        fi
    done

    # Dry run mode
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "DRY RUN MODE - No tools will be executed"
        for stage in $stages; do
            log_info "Would run stage: $stage"
            local stage_tools=$(get_stage_info "$stage" "tools")
            for tool in $stage_tools; do
                if is_tool_enabled "$tool"; then
                    log_verbose "  - $tool (enabled)"
                else
                    log_debug "  - $tool (disabled)"
                fi
            done
        done
        return 0
    fi

    # Create history directory
    local date_stamp=$(date +"%-m-%-d-%Y")
    local history_dir="$project_dir/history/$date_stamp"
    EYE_DATE_STAMP="$date_stamp"
    CURRENT_HISTORY_DIR="$history_dir"
    mkdir -p "$history_dir"
    log_info "History directory: $history_dir"
    init_history_baseline "$project_dir" "$history_dir"

    if [[ "$DIR_ONLY" == "true" ]]; then
        local dir_status=0
        execute_stage dir_enum "$project_dir" "$domain" "$url" || dir_status=$?
        copy_outputs_to_history "$project_dir" "$history_dir"
        return "$dir_status"
    fi

    # Execute each stage
    local failed_stages=0
    local project_status=0
    local bg_pid=""
    for stage in $stages; do
        if [[ "${INTERRUPTED:-false}" == "true" ]]; then
            log_warning "Interrupt requested; stopping remaining stages"
            return 130
        fi

        if [[ "$stage" == "alive_check" || "$stage" == "exact_alive_check" ]]; then
            # Ensure discovered exact-host URLs are available to httpx.
            create_global_urls "$project_dir"
        fi
        if [[ "$stage" == "dir_enum" ]]; then
            # Run directory fuzzing in background after alive_check
            continue
        fi
        local stage_status=0
        execute_stage "$stage" "$project_dir" "$domain" "$url" || stage_status=$?
        if [[ $stage_status -ne 0 ]]; then
            if [[ "${INTERRUPTED:-false}" == "true" ]]; then
                log_warning "Recon interrupted by user"
                return 130
            fi
            failed_stages=$((failed_stages + 1))
            [[ $project_status -eq 0 ]] && project_status=1
            [[ $stage_status -eq 124 ]] && project_status=124
            log_error "Stage $stage failed"
        fi

        if [[ "$profile" == "exact-urls" || "$profile" == "exact-urls-header" ]]; then
            filter_exact_host_artifacts "$project_dir" "$url"
        fi

        if [[ "$stage" == "alive_check" || "$stage" == "exact_alive_check" ]] && [[ "$dir_enum_in_profile" == "true" ]]; then
            if is_stage_enabled "dir_enum"; then
                log_info "Starting directory enumeration in background"
                local bg_dir="$project_dir/.bg_scans"
                mkdir -p "$bg_dir"
                local log_file="$history_dir/dir_enum.log"
                TOOL_TIMEOUT="${TOOL_TIMEOUT:-}" bash "$SCRIPT_DIR/scripts/bg_dir_enum.sh" "$project_dir" "$url" "$history_dir" "$VERBOSE" > "$log_file" 2>&1 &
                bg_pid=$!
                if [[ -n "$bg_pid" ]]; then
                    echo "$bg_pid" > "$bg_dir/dir_enum.pid"
                    log_info "Dir enum running (pid $bg_pid), log: $log_file"
                else
                    log_warning "Failed to start background dir_enum, running in foreground"
                    execute_stage "dir_enum" "$project_dir" "$domain" "$url"
                    copy_outputs_to_history "$project_dir" "$history_dir"
                fi
            else
                log_debug "Stage dir_enum is disabled, skipping background run"
            fi
        fi

        # After each stage, copy outputs to history
        copy_outputs_to_history "$project_dir" "$history_dir"
    done

    # Background work must finish before the project can claim success.
    if [[ -n "$bg_pid" ]]; then
        local bg_status=0
        wait "$bg_pid" || bg_status=$?
        if [[ $bg_status -ne 0 ]]; then
            failed_stages=$((failed_stages + 1))
            [[ $project_status -eq 0 ]] && project_status=1
            [[ $bg_status -eq 124 ]] && project_status=124
        fi
    fi

    # Final summary
    echo ""
    log_info "Recon completed!"
    log_info "Project directory: $project_dir"
    log_info "History saved to: $history_dir"

    if [[ $failed_stages -gt 0 ]]; then
        log_warning "$failed_stages stages had failures"
    else
        log_success "All stages completed successfully"
    fi

    # Show summary of results
    show_results_summary "$project_dir"
    return "$project_status"
}

# Run recon for single URL (stdout only)
run_recon_url_only() {
    local url="$1"
    local profile="$2"

    local domain=$(echo "$url" | sed -e 's|^https\?://||' -e 's|/.*||')
    EYE_DATE_STAMP="$(date +"%-m-%-d-%Y")"
    CURRENT_HISTORY_DIR=""

    log_info "Running recon on: $domain"
    log_info "Profile: $profile"

    # Create temp directory
    local temp_dir=$(mktemp -d)
    local PROJECT_DIR="$temp_dir"
    local RECON_RY_EXACT_HOST="${RECON_RY_EXACT_HOST:-}"
    if [[ "$profile" == "exact-host" || "$profile" == "exact-urls" || "$profile" == "exact-urls-header" ]]; then
        RECON_RY_EXACT_HOST="$url"
    fi
    export RECON_RY_EXACT_HOST
    mkdir -p "$temp_dir/.tmp_run"
    trap "rm -rf $temp_dir" EXIT

    # Get stages for profile
    local stages=$(get_profile_stages "$profile")
    stages=$(reorder_stages_eyewitness_last "$stages")

    if [[ -n "$url" ]]; then
        printf '%s\n' "$url" > "$temp_dir/url_seed.txt"
    fi

    # Execute stages without losing failure/timeout status to result printing.
    local result=0 stage_status=0
    for stage in $stages; do
        stage_status=0
        execute_stage "$stage" "$temp_dir" "$domain" "$url" || stage_status=$?
        [[ $result -eq 0 && $stage_status -ne 0 ]] && result=$stage_status
        [[ $stage_status -eq 124 ]] && result=124
        [[ $stage_status -eq 130 ]] && return 130
    done

    # Output results to stdout
    echo ""
    echo "=== Results ==="
    for file in urls.txt wild.txt alive.txt params.txt; do
        if [[ -s "$temp_dir/$file" ]]; then
            echo ""
            echo "=== $file ==="
            cat "$temp_dir/$file"
        fi
    done
    return "$result"
}

# Show results summary
show_results_summary() {
    local project_dir="$1"

    echo ""
    log_info "Results Summary:"

    for file in wild.txt urls.txt alive.txt params.txt secrets.txt dirs.txt ips.txt hosts.jsonl httpx_ip_raw.txt naabu.jsonl ports.txt httpx.jsonl waf_hosts.txt unprotected_hosts.txt review_queue.jsonl; do
        if [[ -f "$project_dir/$file" ]]; then
            local count=$(wc -l < "$project_dir/$file" 2>/dev/null || echo 0)
            printf "  %-15s: %d entries\n" "$file" "$count"
        fi
    done
}
