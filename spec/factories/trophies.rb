FactoryBot.define do
  factory :trophy do
    bjcp_score 35
    competition
    place 1
    place_context Trophy::PLACE_CONTEXTS.first
    recipe_url "http://recipe.example.com"
    subcategory
    user

    Trophy::PLACE_CONTEXTS.each do |context|
      (1..3).each do |num|
        trait :"#{context}_#{num.ordinalize}" do
          place num
          place_context context
        end
      end
    end
  end
end
