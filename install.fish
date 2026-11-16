# fish: source install.fish
set -l agentdev_source (dirname (status filename))
if sh "$agentdev_source/setup.sh" $argv
    set -l agentdev_install_home $AGENTDEV_HOME
    if test -z "$agentdev_install_home"
        if test -f "$agentdev_source/.agentdev-app"
            set agentdev_install_home (dirname "$agentdev_source")
        else
            set agentdev_install_home "$HOME/.agent-dev-workspace"
        end
    end
    source "$agentdev_install_home/env.fish"
    echo 'agentdev 已在当前 fish 会话生效。'
else
    return $status
end
