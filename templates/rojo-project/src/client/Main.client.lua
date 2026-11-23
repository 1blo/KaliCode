--!strict
-- Client entry point. Runs once per player on their device.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")

local Config = require(ReplicatedStorage.Shared.Config)
local player = Players.LocalPlayer

local function setupCharacter()
    local character = player.Character
    if not character then
        return
    end
    local humanoid = character:WaitForChild("Humanoid", 10)
    if humanoid then
        humanoid.WalkSpeed = Config.playerSpeed
    end
end

player.CharacterAdded:Connect(setupCharacter)
if player.Character then
    setupCharacter()
end

print(`[client] {Config.gameName} loaded`)
