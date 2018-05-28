FactoryBot.define do
  factory :trophy do
    bjcp_score 35
    competition_date { Date.yesterday }
    competition_url "http://comp.example.com"
    place 1
    place_context Trophy::PLACE_CONTEXTS.first
    recipe_url "http://recipe.example.com"
    subcategory
    user
  end
end
