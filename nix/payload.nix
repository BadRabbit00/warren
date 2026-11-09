# br payload. Output:
#   $out/claude/{CLAUDE.md,agents,skills,commands,workflows,rules/br,output-styles,br/templates}
#   $out/settings.fragment.json   env + outputStyle, merged into ~/.claude/settings.json
#   $out/hooks.json               br:* hooks pointing at the pinned br-hook
#   $out/LICENSE                  the payload ships MIT-licensed skills
{
  lib,
  stdenvNoCC,
  git,
  python,
  brHook,
}:
let
  root = ../.;
  # Only the installed directories, tools/ for checkPhase and nix/payload.py for its tests: editing
  # the other nix/ files, README or .plan does not rebuild the payload.
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      ../agents
      ../rules
      ../skills
      ../commands
      ../core
      ../output-styles
      ../templates
      ../workflows
      ../hooks
      ../tools
      # payload.py itself: tools/test_validate.py runs it in subprocess tests.
      ../nix/payload.py
      ../agent-models.json
      ../settings.fragment.json
      ../LICENSE
    ];
  };
in
stdenvNoCC.mkDerivation {
  pname = "br-payload";
  version = "0.3.0";
  inherit src;

  dontConfigure = true;
  dontBuild = true;
  nativeBuildInputs = [ python ];
  # git: the hook tests create throwaway repositories.
  nativeCheckInputs = [ git ];

  # The validator and every Python test run in the build; a red test fails the payload.
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    export HOME="$TMPDIR/home"; mkdir -p "$HOME"
    export GIT_AUTHOR_NAME=nix GIT_AUTHOR_EMAIL=nix@localhost GIT_COMMITTER_NAME=nix GIT_COMMITTER_EMAIL=nix@localhost
    python3 -I -B tools/validate.py .
    python3 -I -B -m unittest discover -s tools -p 'test_*.py'
    (cd hooks && python3 -I -B -m unittest discover -s test)
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    c="$out/claude"
    mkdir -p "$c"/{agents,skills,commands,workflows,rules/br,output-styles,br/templates}

    cp core/CLAUDE.md "$c/CLAUDE.md"
    cp LICENSE "$out/LICENSE"
    cp settings.fragment.json "$out/settings.fragment.json"
    cp output-styles/*.md "$c/output-styles/"
    cp rules/*.md "$c/rules/br/"
    cp -r templates/. "$c/br/templates/"
    cp agents/*.md "$c/agents/"
    cp commands/*.md "$c/commands/"
    cp workflows/*.js "$c/workflows/"
    cp -r skills/. "$c/skills/"
    chmod -R u+w "$out"

    # Frontmatter, contract, hooks.json and self-checks.
    python3 -I -B ${./payload.py} "$out" "$PWD" ${lib.getExe brHook}
    runHook postInstall
  '';

  # Exercises the production path (python -I -B from the filtered store tree) once per build.
  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck
    rc=0
    echo '{"hook_event_name":"PreToolUse","tool_name":"Read","tool_input":{"file_path":"/tmp/x"},"cwd":"/tmp"}' \
      | ${lib.getExe brHook} guard_read || rc=$?
    if [ "$rc" -ne 0 ]; then echo "br-hook guard_read: expected rc 0, got $rc" >&2; exit 1; fi
    rc=0
    ${lib.getExe brHook} nope || rc=$?
    if [ "$rc" -ne 2 ]; then echo "br-hook nope: expected rc 2, got $rc" >&2; exit 1; fi
    runHook postInstallCheck
  '';

  meta = {
    description = "br payload for Claude Code: orchestrator style, isolated agents, path rules, br hooks";
    homepage = "https://github.com/BadRabbit00/warren";
    license = lib.licenses.mit;
  };
}
