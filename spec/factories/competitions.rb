FactoryBot.define do
  factory :competition do
    competition_type CompetitionType::TYPES.first
    date { Date.today }
    name "MyString"
    url "MyString"

    trait :high_profile do
      competition_type "nhc_finals"
    end
  end
end
