FactoryBot.define do
  factory :trophy do
    bjcp_score 35
    competition
    place 1
    place_context Trophy::PLACE_CONTEXTS.first
    recipe_url "http://recipe.example.com"
    subcategory
    user
  end
end
