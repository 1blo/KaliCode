--!strict
-- Server entry point. Runs on the server for every player.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)

local PlayersFolder = Instance.new("Folder")
PlayersFolder.Name = "Players"
PlayersFolder.Parent = ReplicatedStorage

local function onPlayerAdded(player: Player)
    local entry = Instance.new("IntValue")
    entry.Name = "Score"
    entry.Value = 0
    entry.Parent = PlayersFolder

    print(`[server] {player.Name} joined`)
end

local function onPlayerRemoving(player: Player)
    print(`[server] {player.Name} left`)
end

Players.PlayerAdded:Connect(onPlayerAdded)
Players.PlayerRemoving:Connect(onPlayerRemoving)

print(`[server] {Config.gameName} ready (speed={Config.playerSpeed})`)
